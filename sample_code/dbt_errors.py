# sample9_dbt_errors.py
# dbt Python models + orchestration script — portfolio analytics pipeline.
# INTENTIONALLY BUGGY — use as: python main.py sample_code/sample9_dbt_errors.py
#
# dbt supports Python models natively on Databricks/Snowflake.
# This file contains common dbt anti-patterns and security mistakes.

import subprocess
import os
import requests

# ── Security: Hardcoded warehouse credentials ─────────────────────────────────
SNOWFLAKE_PASSWORD = "aimco_snowflake_prod_2024!"
SNOWFLAKE_ACCOUNT  = "aimco.snowflakecomputing.com"
DBT_TARGET         = "prod"


# ════════════════════════════════════════════════════════════════════════════════
# dbt PYTHON MODEL 1 — portfolio_returns
# This is a dbt Python model (saved as models/marts/portfolio_returns.py in dbt)
# ════════════════════════════════════════════════════════════════════════════════

def model(dbt, session):
    """
    Calculates daily portfolio returns by joining trades with benchmarks.

    Problems:
    - Uses hardcoded table names instead of dbt.ref() / dbt.source()
    - Hardcoded date filter — will never pick up new data after 2024
    - No incremental strategy — full refresh every run (expensive)
    - Exposes raw client PII (name, SIN) in the output model
    - No null handling on join — silent data loss
    """

    # Bug: hardcoded table path — breaks if the schema or database changes,
    # and bypasses dbt's lineage graph (dbt doesn't know this model depends on these tables)
    trades_df = session.table("RAW_DB.FINANCE.TRADES")
    clients_df = session.table("RAW_DB.FINANCE.CLIENTS")

    # Bug: hardcoded date — this model silently returns no new rows after 2024-12-31
    trades_df = trades_df.filter(trades_df["TRADE_DATE"] >= "2024-01-01")

    result = trades_df.join(clients_df, on="CLIENT_ID", how="inner")

    # Bug: inner join silently drops trades with no matching client —
    # a LEFT JOIN with a null check would surface the data quality issue

    # Security: SIN (Social Insurance Number) and full name exposed in output —
    # should be masked or excluded from this model
    return result.select(
        "TRADE_ID", "CLIENT_ID",
        "CLIENT_NAME",        # PII
        "CLIENT_SIN",         # PII — highly sensitive
        "TRADE_DATE", "TICKER", "TRADE_AMOUNT", "PNL"
    )


# ════════════════════════════════════════════════════════════════════════════════
# dbt PYTHON MODEL 2 — risk_concentration
# ════════════════════════════════════════════════════════════════════════════════

def model(dbt, session):          # Bug: duplicate function name — silently overwrites the first model!
    """
    Calculates concentration risk per portfolio.

    Problems:
    - No model config (materialization, tags, description not set)
    - Pulls all rows to the driver with .toPandas() instead of staying in Spark
    - No schema tests anywhere in the project
    - Division by zero not guarded
    """

    # Bug: no dbt.config() call — model materializes as a view (default),
    # which means the expensive query re-runs every time it's queried downstream
    # dbt.config(materialized="table") should be declared here

    holdings = dbt.ref("stg_holdings")    # At least ref() is used here

    pdf = holdings.toPandas()             # Bug: pulls entire holdings table to driver

    # Bug: ZeroDivisionError if total_value is 0 for any portfolio
    pdf["weight"] = pdf["market_value"] / pdf.groupby("portfolio_id")["market_value"].transform("sum")
    pdf["is_concentrated"] = pdf["weight"] > 0.25

    return session.createDataFrame(pdf)


# ════════════════════════════════════════════════════════════════════════════════
# dbt PYTHON MODEL 3 — enriched_positions (fetches live prices from external API)
# ════════════════════════════════════════════════════════════════════════════════

def model(dbt, session):          # Bug: third duplicate function name
    """
    Enriches positions with live market prices.

    Problems:
    - Makes external HTTP calls inside a dbt model (breaks idempotency)
    - API key hardcoded in model source
    - No retry or error handling on API call
    - Row-by-row loop instead of a batch API call
    """

    MARKET_DATA_KEY = "mkt-live-key-abc123"     # Security: hardcoded API key

    positions = dbt.ref("stg_positions").toPandas()

    prices = []
    for _, row in positions.iterrows():     # Bug: Python row-by-row loop — very slow
        # Bug: no error handling — one failed API call crashes the entire model run
        resp = requests.get(
            f"https://api.marketdata.com/price/{row['ticker']}",
            headers={"X-API-Key": MARKET_DATA_KEY}
        )
        prices.append(resp.json()["price"])  # Bug: no status check, KeyError if field missing

    positions["live_price"] = prices
    return session.createDataFrame(positions)


# ════════════════════════════════════════════════════════════════════════════════
# dbt ORCHESTRATION — runs the pipeline
# ════════════════════════════════════════════════════════════════════════════════

def run_dbt_pipeline(models: list):
    """Run the dbt models using the CLI."""

    for model_name in models:
        # Security: model_name is passed directly to shell — command injection.
        # A model name of "portfolio; rm -rf /" would execute the second command.
        cmd = f"dbt run --select {model_name} --target {DBT_TARGET} --profiles-dir ."
        os.system(cmd)   # Bug: os.system() — return code ignored, errors silently swallowed

    # Bug: --profiles-dir . means dbt reads profiles.yml from the current directory,
    # which contains the hardcoded password above — this gets logged by dbt


def run_dbt_tests():
    """Run dbt schema tests."""
    # Bug: no tests are actually defined in schema.yml, so this always passes vacuously
    os.system("dbt test")


def generate_docs():
    """Generate and serve dbt docs."""
    # Security: starts a public web server without any authentication
    # Anyone on the network can browse the full data lineage and model SQL
    os.system("dbt docs generate && dbt docs serve --port 8080 --host 0.0.0.0")


if __name__ == "__main__":
    run_dbt_pipeline(["portfolio_returns", "risk_concentration", "enriched_positions"])
    run_dbt_tests()
    generate_docs()
