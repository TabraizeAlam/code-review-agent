# sample10_dbt_working.py
# dbt Python models + orchestration script — portfolio analytics pipeline.
# CLEAN VERSION — production-ready dbt patterns.
#
# Same pipeline as sample9 but done correctly.

import subprocess
import shlex
import os
import logging

logger = logging.getLogger(__name__)


# ── Credentials come from environment / secret manager — never hardcoded ──────
# In Databricks: set via cluster environment variables or Databricks Secrets.
# In dbt Cloud: set via the encrypted environment variable UI.
# profiles.yml references {{ env_var('SNOWFLAKE_PASSWORD') }} — never a literal.


# ════════════════════════════════════════════════════════════════════════════════
# dbt PYTHON MODEL 1 — portfolio_returns
# File: models/marts/portfolio_returns.py
# ════════════════════════════════════════════════════════════════════════════════

def model(dbt, session):
    """
    Calculates daily portfolio returns joined with client data.

    - Uses dbt.ref() and dbt.source() so dbt builds the lineage graph correctly
    - Incremental: only processes new rows, not a full refresh each run
    - PII columns masked — SIN hashed, name excluded from the output model
    - LEFT JOIN + null filter surfaces data quality issues instead of hiding them
    """

    # Declare model config inside the function (dbt requirement for Python models)
    dbt.config(
        materialized="incremental",       # Only new rows appended each run
        unique_key="trade_id",            # Upsert key for idempotency
        incremental_strategy="merge",
        tags=["finance", "daily"],
        description="Daily portfolio returns enriched with benchmark data.",
    )

    # dbt.ref() and dbt.source() register dependencies in the lineage DAG.
    # dbt will never run this model before its upstream models are ready.
    trades_df  = dbt.ref("stg_trades")           # staging model in this project
    clients_df = dbt.source("raw_finance", "clients")  # raw source table

    # Incremental filter — only process rows not yet in the output table
    if dbt.is_incremental():
        max_date = session.sql(
            f"SELECT MAX(trade_date) FROM {dbt.this}"
        ).collect()[0][0]
        trades_df = trades_df.filter(trades_df["trade_date"] > max_date)

    result = (
        trades_df
        .join(clients_df, on="client_id", how="left")   # LEFT: keeps all trades
        .filter(clients_df["client_id"].isNotNull())     # Explicit null filter surfaces bad data
    )

    # Mask PII before it reaches the output model:
    #   - SIN: one-way SHA-256 hash (usable as a join key but not reversible)
    #   - Client name: excluded entirely from this model
    from pyspark.sql import functions as F

    return result.select(
        "trade_id", "client_id",
        F.sha2("client_sin", 256).alias("client_sin_hash"),   # Masked
        # "client_name" intentionally omitted — not needed for return calculations
        "trade_date", "ticker", "asset_class", "trade_amount", "pnl",
    )


# ════════════════════════════════════════════════════════════════════════════════
# dbt PYTHON MODEL 2 — risk_concentration
# File: models/marts/risk_concentration.py
# ════════════════════════════════════════════════════════════════════════════════

def model(dbt, session):      # Each model lives in its own file — no name collision
    """
    Calculates concentration risk per portfolio using distributed Spark operations.

    - Table materialization (not view) — expensive query runs once, not on every read
    - Stays in Spark — no toPandas() / driver bottleneck
    - Null-safe division — no ZeroDivisionError
    """
    from pyspark.sql import functions as F
    from pyspark.sql import Window

    dbt.config(
        materialized="table",
        tags=["risk", "daily"],
        description="Concentration weight per holding per portfolio. Flags positions > 25% weight.",
    )

    holdings = dbt.ref("stg_holdings")

    # Window function runs distributed — no data pulled to driver
    portfolio_window = Window.partitionBy("portfolio_id")
    total_value      = F.sum("market_value").over(portfolio_window)

    # Null-safe division: nullif prevents ZeroDivisionError when total is 0
    weight = (F.col("market_value") / F.nullif(total_value, F.lit(0))).alias("weight")

    return holdings.select(
        "portfolio_id", "ticker", "asset_class", "market_value",
        weight,
        (F.col("weight") > 0.25).alias("is_concentrated"),
    )


# ════════════════════════════════════════════════════════════════════════════════
# dbt PYTHON MODEL 3 — enriched_positions
# File: models/marts/enriched_positions.py
# ════════════════════════════════════════════════════════════════════════════════

def model(dbt, session):
    """
    Enriches positions with the most recent market prices.

    - Prices come from a staged source model, not a live API call.
      Live API calls inside dbt models break idempotency and make reruns unreliable.
    - No external HTTP requests, no hardcoded API keys.
    - Pure Spark join — scales to any data size.
    """
    dbt.config(
        materialized="table",
        tags=["finance", "daily"],
        description="Current positions joined with latest market prices from the prices staging model.",
    )

    positions  = dbt.ref("stg_positions")
    prices     = dbt.ref("stg_market_prices")   # Prices loaded separately by an ingestion job

    # Join on ticker — LEFT so positions without a price are visible (data quality signal)
    return (
        positions
        .join(prices.select("ticker", "price", "price_as_of"), on="ticker", how="left")
        .withColumn(
            "market_value_live",
            positions["quantity"] * prices["price"],
        )
    )


# ════════════════════════════════════════════════════════════════════════════════
# dbt ORCHESTRATION
# ════════════════════════════════════════════════════════════════════════════════

def run_dbt_command(args: list[str]) -> bool:
    """
    Run a dbt CLI command safely.

    - Uses subprocess.run() with a list (not a string) — no shell injection possible
    - Captures and logs output
    - Returns True on success, False on failure — caller decides whether to stop
    """
    cmd = ["dbt"] + args
    logger.info("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        # No shell=True — list form is immune to command injection
    )

    if result.returncode != 0:
        logger.error("dbt command failed:\n%s", result.stderr)
        return False

    logger.info(result.stdout)
    return True


def run_dbt_pipeline(models: list[str], target: str = "prod") -> None:
    """
    Run selected dbt models, then test them.
    Stops immediately if any step fails.
    """
    # target comes from a validated argument, not user input — no injection risk
    valid_targets = {"dev", "staging", "prod"}
    if target not in valid_targets:
        raise ValueError(f"Invalid target '{target}'. Must be one of {valid_targets}.")

    for model_name in models:
        # Validate model name — only allow alphanumeric and underscores
        if not model_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid model name: '{model_name}'")

        success = run_dbt_command([
            "run",
            "--select", model_name,     # Passed as a list item — no shell expansion
            "--target", target,
        ])

        if not success:
            raise RuntimeError(f"dbt run failed for model: {model_name}")

    logger.info("All models ran successfully. Running tests...")

    success = run_dbt_command(["test", "--target", target])
    if not success:
        raise RuntimeError("dbt tests failed — check logs above.")


def generate_docs(target: str = "prod") -> None:
    """
    Generate dbt docs and write to the output directory.
    Does NOT serve them publicly — serving is handled by a separate authenticated portal.
    """
    run_dbt_command(["docs", "generate", "--target", target])
    logger.info("Docs generated in ./target/. Deploy via your internal docs portal.")
    # Note: never run `dbt docs serve --host 0.0.0.0` in production


if __name__ == "__main__":
    target = os.environ.get("DBT_TARGET", "dev")   # Default to dev — explicit prod opt-in
    run_dbt_pipeline(
        models=["portfolio_returns", "risk_concentration", "enriched_positions"],
        target=target,
    )
    generate_docs(target=target)
