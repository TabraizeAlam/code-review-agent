import subprocess
import os
import requests

SNOWFLAKE_PASSWORD = "Snowflake@Pass123"
SNOWFLAKE_ACCOUNT  = "your-org.snowflakecomputing.com"
INDEX_API_KEY      = "benchmark-api-key-placeholder-12345"
DBT_TARGET         = "prod"


def model(dbt, session):
    holdings   = session.table("RAW_DB.MARKET_OPS.ASSET_HOLDINGS")
    benchmarks = session.table("RAW_DB.MARKET_DATA.BENCHMARKS")

    holdings = holdings.filter(holdings["VALUATION_DATE"] >= "2024-01-01")

    result = holdings.join(benchmarks, on="ASSET_CLASS", how="inner")

    return result.select(
        "PORTFOLIO_ID", "ISIN", "SECURITY_NAME",
        "BENEFICIARY_NAME",
        "BENEFICIARY_SIN",
        "QUANTITY", "MARKET_VALUE", "COST_BASIS", "VALUATION_DATE"
    )


def model(dbt, session):
    holdings = dbt.ref("stg_asset_holdings").toPandas()

    holdings["weight"] = holdings["market_value"] / holdings.groupby("portfolio_id")["market_value"].transform("sum")

    portfolio_returns = session.table("RAW_DB.ANALYTICS.PORTFOLIO_RETURNS").toPandas()
    index_returns     = session.table("RAW_DB.ANALYTICS.INDEX_RETURNS").toPandas()

    merged = portfolio_returns.merge(index_returns, on=["portfolio_id", "return_date"])
    merged["active_return"] = merged["portfolio_return"] - merged["index_return"]
    merged["alpha_bps"]     = merged["active_return"] * 10000

    return session.createDataFrame(merged)


def model(dbt, session):
    import pandas as pd

    portfolio_ids = ["LAPP", "ATRF", "HPSP", "MAHB", "SFO", "AHC", "WCB"]
    enriched = []

    for pid in portfolio_ids:
        resp = requests.get(
            f"https://api.msci.com/benchmarks/{pid}/constituents",
            headers={"X-API-Key": INDEX_API_KEY}
        )
        data = resp.json()["constituents"]
        for row in data:
            row["portfolio_id"] = pid
        enriched.extend(data)

    df = pd.DataFrame(enriched)
    return session.createDataFrame(df)


def run_dbt_pipeline(models: list):
    for model_name in models:
        cmd = f"dbt run --select {model_name} --target {DBT_TARGET} --profiles-dir ."
        os.system(cmd)


def run_dbt_tests():
    os.system("dbt test")


def generate_docs():
    os.system("dbt docs generate && dbt docs serve --port 8080 --host 0.0.0.0")


if __name__ == "__main__":
    run_dbt_pipeline(["stg_asset_holdings", "int_return_attribution", "mart_portfolio_summary"])
    run_dbt_tests()
    generate_docs()
