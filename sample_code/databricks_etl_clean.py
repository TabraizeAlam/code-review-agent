from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType, LongType
import logging

logger = logging.getLogger(__name__)
spark = SparkSession.builder.appName("PortfolioDataPipeline").getOrCreate()

ADLS_ACCOUNT  = "investmentdatalake"
PORTFOLIO_IDS = ["FUND_A", "FUND_B", "FUND_C", "FUND_D", "FUND_E", "FUND_F", "FUND_G"]

HOLDINGS_SCHEMA = StructType([
    StructField("portfolio_id",   StringType(), nullable=False),
    StructField("isin",           StringType(), nullable=False),
    StructField("security_name",  StringType(), nullable=True),
    StructField("asset_class",    StringType(), nullable=True),
    StructField("quantity",       DoubleType(), nullable=False),
    StructField("market_value",   DoubleType(), nullable=False),
    StructField("cost_basis",     DoubleType(), nullable=True),
    StructField("valuation_date", DateType(),   nullable=False),
])


def get_secrets() -> dict:
    return {
        "adls_key":     dbutils.secrets.get(scope="investment-kv", key="adls-storage-key"),
        "sql_password": dbutils.secrets.get(scope="investment-kv", key="databricks-sql-password"),
        "sql_user":     dbutils.secrets.get(scope="investment-kv", key="databricks-sql-user"),
    }


def mount_storage() -> None:
    secrets = get_secrets()
    for container in ["raw", "bronze", "silver", "gold"]:
        mount_point = f"/mnt/investment-{container}"
        already_mounted = any(m.mountPoint == mount_point for m in dbutils.fs.mounts())
        if not already_mounted:
            dbutils.fs.mount(
                source=f"abfss://{container}@{ADLS_ACCOUNT}.dfs.core.windows.net",
                mount_point=mount_point,
                extra_configs={
                    f"fs.azure.account.key.{ADLS_ACCOUNT}.dfs.core.windows.net": secrets["adls_key"]
                }
            )
            logger.info("Mounted %s", mount_point)


def ingest_holdings_bronze(report_date: str) -> int:
    file_path = f"/mnt/investment-raw/third_party/holdings/{report_date}/*.csv"

    try:
        df = (
            spark.read
            .schema(HOLDINGS_SCHEMA)
            .option("header", "true")
            .option("mode", "PERMISSIVE")
            .csv(file_path)
        )

        missing_cols = [f.name for f in HOLDINGS_SCHEMA.fields if f.name not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing columns in holdings file: {missing_cols}")

        row_count = df.count()

        df.write.format("delta").mode("append").save(
            f"/mnt/investment-bronze/holdings/{report_date}"
        )

        logger.info("Bronze ingest: %d holding records for %s", row_count, report_date)
        return row_count

    except Exception as exc:
        logger.error("Bronze ingest failed for %s: %s", report_date, exc)
        raise


def ingest_index_returns_bronze() -> None:
    secrets = get_secrets()
    jdbc_url = (
        "jdbc:sqlserver://inv-sql-server.database.windows.net:1433;"
        "database=MarketData;encrypt=true;trustServerCertificate=false;"
    )

    df = (
        spark.read
        .format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", "dbo.IndexReturns")
        .option("user", secrets["sql_user"])
        .option("password", secrets["sql_password"])
        .option("numPartitions", "4")
        .load()
    )

    df.write.format("delta").mode("overwrite").save("/mnt/investment-bronze/index_returns")


def build_silver_holdings(report_date: str) -> None:
    df = spark.read.format("delta").load(f"/mnt/investment-bronze/holdings/{report_date}")

    cleaned_df = (
        df
        .filter(F.col("market_value").isNotNull() & (F.col("market_value") > 0))
        .filter(F.col("quantity") > 0)
        .filter(F.col("portfolio_id").isin(PORTFOLIO_IDS))
        .filter(F.col("isin").isNotNull())
        .withColumn("ingested_at", F.current_timestamp())
    )

    invalid_count = df.count() - cleaned_df.count()
    if invalid_count > 0:
        logger.warning("Dropped %d invalid rows during silver transform", invalid_count)

    cleaned_df.write.format("delta").mode("overwrite").save(
        f"/mnt/investment-silver/holdings/{report_date}"
    )


def build_gold_portfolio_summary(report_date: str) -> None:
    holdings = spark.read.format("delta").load(f"/mnt/investment-silver/holdings/{report_date}")
    holdings.cache()

    try:
        aum_by_portfolio = (
            holdings
            .groupBy("portfolio_id")
            .agg(
                F.sum("market_value").alias("total_aum"),
                F.countDistinct("isin").alias("num_holdings"),
            )
        )

        aum_by_asset = (
            holdings
            .groupBy("portfolio_id", "asset_class")
            .agg(F.sum("market_value").alias("asset_class_mv"))
        )

        aum_by_portfolio.write.format("delta").mode("overwrite").save(
            f"/mnt/investment-gold/portfolio_summary/{report_date}"
        )
        aum_by_asset.write.format("delta").mode("overwrite").save(
            f"/mnt/investment-gold/asset_class_summary/{report_date}"
        )

        logger.info("Gold portfolio summary written for %s", report_date)

    finally:
        holdings.unpersist()


def run_pipeline(report_date: str) -> None:
    try:
        mount_storage()
        row_count = ingest_holdings_bronze(report_date)
        ingest_index_returns_bronze()
        build_silver_holdings(report_date)
        build_gold_portfolio_summary(report_date)
        logger.info("Pipeline complete for %s — %d records processed", report_date, row_count)
    except Exception as exc:
        logger.error("Pipeline failed for %s: %s", report_date, exc)
        raise
