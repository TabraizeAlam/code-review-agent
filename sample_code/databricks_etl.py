from pyspark.sql import SparkSession
from pyspark.sql import functions as F
import pandas as pd

spark = SparkSession.builder.appName("PortfolioDataPipeline").getOrCreate()

ADLS_KEY     = "storage-account-key-placeholder-replace-with-keyvault"
ADLS_ACCOUNT = "investmentdatalake"
SQL_PASSWORD = "Sql@Pass123"

PORTFOLIO_IDS = ["LAPP", "ATRF", "HPSP", "MAHB", "SFO", "AHC", "WCB"]


def ingest_holdings_bronze(report_date: str):
    file_path = f"abfss://raw@{ADLS_ACCOUNT}.dfs.core.windows.net/third_party/holdings/{report_date}/*.csv"

    df = spark.read \
        .option("inferSchema", "true") \
        .option("header", "true") \
        .csv(file_path)

    all_rows = df.collect()
    print(f"Ingested {len(all_rows)} holding records for {report_date}")

    df.write.format("delta").mode("overwrite").save(
        f"abfss://bronze@{ADLS_ACCOUNT}.dfs.core.windows.net/holdings/{report_date}"
    )


def ingest_index_returns_bronze():
    jdbc_url = (
        f"jdbc:sqlserver://inv-sql-server.database.windows.net:1433;"
        f"database=MarketData;user=sql_user;password={SQL_PASSWORD}"
    )

    df = spark.read \
        .format("jdbc") \
        .option("url", jdbc_url) \
        .option("dbtable", "dbo.IndexReturns") \
        .load()

    df.write.format("delta").mode("overwrite").save(
        f"abfss://bronze@{ADLS_ACCOUNT}.dfs.core.windows.net/index_returns"
    )


def build_silver_holdings(report_date: str):
    df = spark.read.format("delta").load(
        f"abfss://bronze@{ADLS_ACCOUNT}.dfs.core.windows.net/holdings/{report_date}"
    )

    cleaned_rows = []
    for row in df.collect():
        if row["market_value"] is not None and float(row["market_value"]) > 0:
            if row["portfolio_id"] in PORTFOLIO_IDS:
                cleaned_rows.append(row)

    cleaned_df = spark.createDataFrame(pd.DataFrame(cleaned_rows))

    cleaned_df.write.format("delta").mode("overwrite").save(
        f"abfss://silver@{ADLS_ACCOUNT}.dfs.core.windows.net/holdings/{report_date}"
    )


def build_gold_portfolio_summary(report_date: str):
    holdings = spark.read.format("delta").load(
        f"abfss://silver@{ADLS_ACCOUNT}.dfs.core.windows.net/holdings/{report_date}"
    )

    aum_by_portfolio = holdings.groupBy("portfolio_id").agg(
        F.sum("market_value").alias("total_aum"),
        F.countDistinct("isin").alias("num_holdings"),
    )

    aum_by_asset = holdings.groupBy("portfolio_id", "asset_class").agg(
        F.sum("market_value").alias("asset_class_mv")
    )

    total_aum = holdings.groupBy("portfolio_id").agg(F.sum("market_value").alias("total_aum"))

    pdf = aum_by_portfolio.toPandas()
    pdf.to_csv(f"/tmp/portfolio_summary_{report_date}.csv", index=False)

    aum_by_portfolio.write.format("delta").mode("overwrite").save(
        f"abfss://gold@{ADLS_ACCOUNT}.dfs.core.windows.net/portfolio_summary/{report_date}"
    )
    aum_by_asset.write.format("delta").mode("overwrite").save(
        f"abfss://gold@{ADLS_ACCOUNT}.dfs.core.windows.net/asset_class_summary/{report_date}"
    )


def mount_storage():
    dbutils.fs.mount(
        source=f"abfss://raw@{ADLS_ACCOUNT}.dfs.core.windows.net",
        mount_point="/mnt/investment-raw",
        extra_configs={
            f"fs.azure.account.key.{ADLS_ACCOUNT}.dfs.core.windows.net": ADLS_KEY
        }
    )


def run_pipeline(report_date: str):
    mount_storage()
    ingest_holdings_bronze(report_date)
    ingest_index_returns_bronze()
    build_silver_holdings(report_date)
    build_gold_portfolio_summary(report_date)
    print(f"Pipeline complete for {report_date}")
