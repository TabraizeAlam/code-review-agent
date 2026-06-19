import subprocess
import os
import logging

logger = logging.getLogger(__name__)

PORTFOLIO_IDS = ["LAPP", "ATRF", "HPSP", "MAHB", "SFO", "AHC", "WCB"]
VALID_TARGETS = {"dev", "staging", "prod"}


def model(dbt, session):
    from pyspark.sql import functions as F

    dbt.config(
        materialized="incremental",
        unique_key=["portfolio_id", "isin", "valuation_date"],
        incremental_strategy="merge",
        tags=["data_provider", "daily"],
    )

    holdings   = dbt.source("data_provider", "raw_holdings")
    securities = dbt.ref("stg_securities")

    if dbt.is_incremental():
        max_date = session.sql(f"SELECT MAX(valuation_date) FROM {dbt.this}").collect()[0][0]
        holdings = holdings.filter(holdings["valuation_date"] > max_date)

    return (
        holdings
        .join(securities.select("isin", "asset_class", "sector", "country"), on="isin", how="left")
        .filter(F.col("market_value").isNotNull() & (F.col("market_value") > 0))
        .filter(F.col("portfolio_id").isin(PORTFOLIO_IDS))
        .select(
            "portfolio_id", "isin", "security_name", "asset_class",
            "sector", "country", "quantity", "market_value", "cost_basis", "valuation_date"
        )
    )


def model(dbt, session):
    from pyspark.sql import functions as F

    dbt.config(
        materialized="table",
        tags=["performance", "monthly"],
    )

    holdings      = dbt.ref("stg_asset_holdings")
    portfolio_ret = dbt.ref("stg_portfolio_returns")
    index_ret     = dbt.ref("stg_index_returns")
    index_mapping = dbt.ref("seed_portfolio_index_map")

    portfolio_with_index = portfolio_ret.join(index_mapping, on="portfolio_id", how="left")

    attribution = (
        portfolio_with_index
        .join(index_ret, on=["index_name", "return_date"], how="left")
        .withColumn("active_return", F.col("portfolio_return") - F.col("index_return"))
        .withColumn("alpha_bps", (F.col("active_return") * 10000).cast("decimal(10,2)"))
    )

    return attribution.select(
        "portfolio_id", "index_name", "return_date",
        "portfolio_return", "index_return", "active_return", "alpha_bps"
    )


def model(dbt, session):
    from pyspark.sql import functions as F
    from pyspark.sql import Window

    dbt.config(
        materialized="table",
        tags=["reporting", "daily"],
    )

    holdings    = dbt.ref("stg_asset_holdings")
    attribution = dbt.ref("int_return_attribution")

    portfolio_window = Window.partitionBy("portfolio_id")

    holdings_with_weight = holdings.withColumn(
        "weight",
        F.col("market_value") / F.nullif(F.sum("market_value").over(portfolio_window), F.lit(0))
    )

    aum_summary = (
        holdings_with_weight
        .groupBy("portfolio_id", "valuation_date")
        .agg(
            F.sum("market_value").alias("total_aum"),
            F.countDistinct("isin").alias("num_holdings"),
        )
    )

    latest_attribution = (
        attribution
        .groupBy("portfolio_id")
        .agg(
            F.sum("alpha_bps").alias("ytd_alpha_bps"),
            F.avg("active_return").alias("avg_active_return"),
        )
    )

    return aum_summary.join(latest_attribution, on="portfolio_id", how="left")


def run_dbt_command(args: list, target: str) -> bool:
    if target not in VALID_TARGETS:
        raise ValueError(f"Invalid target '{target}'")

    cmd = ["dbt"] + args + ["--target", target]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("dbt failed:\n%s", result.stderr)
        return False

    logger.info(result.stdout)
    return True


def run_pipeline(target: str = "dev") -> None:
    models = ["stg_asset_holdings", "int_return_attribution", "mart_portfolio_summary"]

    for model_name in models:
        if not model_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid model name: {model_name}")

        success = run_dbt_command(["run", "--select", model_name], target)
        if not success:
            raise RuntimeError(f"dbt run failed for: {model_name}")

    run_dbt_command(["test", "--select"] + models, target)
    run_dbt_command(["docs", "generate"], target)
    logger.info("Docs generated — deploy via internal portal, do not serve publicly")


if __name__ == "__main__":
    target = os.environ.get("DBT_TARGET", "dev")
    run_pipeline(target=target)
