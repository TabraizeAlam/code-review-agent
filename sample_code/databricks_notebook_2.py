# sample6_databricks_working.py
# Databricks notebook — ETL pipeline for investment portfolio data.
# CLEAN VERSION — the correct patterns for production Databricks notebooks.
#
# Same workflow as sample5 but done right:
#   Bronze (raw ingest) → Silver (cleaned) → Gold (aggregated for reporting)

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, DateType, LongType, TimestampType,
)
import logging

logger = logging.getLogger(__name__)
spark = SparkSession.builder.appName("PortfolioETL").getOrCreate()


# ── Credentials: fetched from Databricks Secret Scope at runtime ──────────────
# Never hardcode keys. dbutils.secrets.get() reads from Azure Key Vault.
# The value is masked in notebook output automatically.
def get_secrets() -> dict:
    return {
        "storage_key": dbutils.secrets.get(scope="aimco-kv", key="adls-storage-key"),
        "jdbc_password": dbutils.secrets.get(scope="aimco-kv", key="portfolio-db-password"),
        "jdbc_user": dbutils.secrets.get(scope="aimco-kv", key="portfolio-db-user"),
    }


# ── Explicit schema — never use inferSchema in production ────────────────────
TRADE_SCHEMA = StructType([
    StructField("trade_id",      StringType(),    nullable=False),
    StructField("portfolio_id",  StringType(),    nullable=False),
    StructField("ticker",        StringType(),    nullable=False),
    StructField("asset_class",   StringType(),    nullable=True),
    StructField("action",        StringType(),    nullable=False),  # BUY | SELL
    StructField("quantity",      DoubleType(),    nullable=False),
    StructField("trade_price",   DoubleType(),    nullable=False),
    StructField("trade_amount",  DoubleType(),    nullable=True),
    StructField("trade_date",    DateType(),      nullable=False),
    StructField("pnl",           DoubleType(),    nullable=True),
])

POSITION_SCHEMA = StructType([
    StructField("portfolio_id",  StringType(),    nullable=False),
    StructField("ticker",        StringType(),    nullable=False),
    StructField("asset_class",   StringType(),    nullable=True),
    StructField("quantity",      DoubleType(),    nullable=False),
    StructField("market_value",  DoubleType(),    nullable=False),
    StructField("as_of_date",    DateType(),      nullable=False),
])


# ── Bronze Layer: Raw Ingest ──────────────────────────────────────────────────

def ingest_trades_bronze(file_path: str) -> int:
    """
    Read raw trade files from ADLS into the Bronze Delta table.
    Returns row count for monitoring.
    """
    try:
        df = (
            spark.read
            .schema(TRADE_SCHEMA)          # Explicit schema — fast and type-safe
            .option("header", "true")
            .option("mode", "PERMISSIVE")  # Bad rows go to _corrupt_record column
            .csv(file_path)
        )

        # Validate schema before writing — catch missing columns early
        missing = [f.name for f in TRADE_SCHEMA.fields if f.name not in df.columns]
        if missing:
            raise ValueError(f"Missing columns in source file: {missing}")

        row_count = df.count()
        logger.info("Ingested %d rows from %s", row_count, file_path)

        (
            df.write
            .format("delta")
            .mode("append")               # Append, not overwrite — preserve history
            .option("mergeSchema", "false")
            .save("/mnt/bronze/trades")
        )

        return row_count

    except Exception as exc:
        logger.error("Bronze ingest failed for %s: %s", file_path, exc)
        raise  # Re-raise so the caller (orchestrator) can handle it


def ingest_positions_jdbc() -> None:
    """Pull current positions from SQL Server into Bronze using secrets."""
    secrets = get_secrets()

    jdbc_url = (
        "jdbc:sqlserver://aimco-prod.database.windows.net:1433;"
        "database=PortfolioDB;"
        "encrypt=true;trustServerCertificate=false;"
    )

    positions_df = (
        spark.read
        .format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", "dbo.Positions")
        .option("user", secrets["jdbc_user"])
        .option("password", secrets["jdbc_password"])  # From Key Vault — never hardcoded
        .option("numPartitions", "8")                  # Parallel reads for performance
        .option("fetchsize", "10000")
        .load()
    )

    (
        positions_df.write
        .format("delta")
        .mode("overwrite")
        .save("/mnt/bronze/positions")
    )


# ── Silver Layer: Clean & Validate ───────────────────────────────────────────

def clean_trades_silver() -> None:
    """Read Bronze trades, clean using Spark transformations, write to Silver."""

    df = spark.read.format("delta").load("/mnt/bronze/trades")

    # Use Spark filter() — runs distributed across all workers, not on the driver
    cleaned_df = (
        df
        .filter(F.col("trade_amount").isNotNull())
        .filter(F.col("trade_amount") > 0)
        .filter(F.col("quantity") > 0)
        .filter(F.col("action").isin("BUY", "SELL"))
        .withColumn("trade_date", F.to_date("trade_date", "yyyy-MM-dd"))
        .withColumn("ingested_at", F.current_timestamp())
    )

    row_count = cleaned_df.count()
    logger.info("Silver: %d clean rows written", row_count)

    (
        cleaned_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "false")
        .save("/mnt/silver/trades")
    )


def enrich_with_benchmarks(portfolio_id: str) -> DataFrame:
    """
    Join portfolio returns with benchmark data.
    Uses a parameterized filter — no SQL injection possible.
    """
    portfolio_df = spark.read.format("delta").load("/mnt/silver/portfolio_returns")
    benchmark_df = spark.read.format("delta").load("/mnt/silver/benchmarks")

    # Filter with a typed column expression — not string interpolation
    result = (
        portfolio_df
        .filter(F.col("portfolio_id") == portfolio_id)   # Safe: value never touches SQL parser
        .join(benchmark_df, on="asset_class", how="left")
        .select(
            "portfolio_id", "asset_class",
            "portfolio_return", "benchmark_return",
            (F.col("portfolio_return") - F.col("benchmark_return")).alias("active_return"),
        )
    )

    return result


# ── Gold Layer: Aggregations for Reporting ───────────────────────────────────

def calculate_daily_pnl() -> None:
    """Aggregate daily P&L per portfolio and asset class."""

    df = spark.read.format("delta").load("/mnt/silver/trades")

    # Cache the DataFrame — it's read 3 times below, so Spark computes it once
    df.cache()

    try:
        total_pnl = (
            df.groupBy("portfolio_id")
            .agg(F.sum("pnl").alias("total_pnl"), F.count("trade_id").alias("num_trades"))
        )

        pnl_by_asset = (
            df.groupBy("portfolio_id", "asset_class")
            .agg(F.sum("pnl").alias("pnl"), F.avg("trade_price").alias("avg_price"))
        )

        total_pnl.write.format("delta").mode("overwrite").save("/mnt/gold/daily_pnl")
        pnl_by_asset.write.format("delta").mode("overwrite").save("/mnt/gold/pnl_by_asset")

    except Exception as exc:
        logger.error("Gold P&L calculation failed: %s", exc)
        raise

    finally:
        df.unpersist()  # Release cache memory even if an error occurred


def generate_risk_report(start_date: str, end_date: str) -> DataFrame:
    """
    Calculate concentration metrics for the risk team.
    Returns a Spark DataFrame — avoids pulling data to the driver.
    """
    positions_df = spark.read.format("delta").load("/mnt/silver/positions")

    # Filter with typed column expressions — not f-string SQL
    filtered = positions_df.filter(
        (F.col("as_of_date") >= start_date) &
        (F.col("as_of_date") <= end_date)
    )

    report_df = (
        filtered
        .groupBy("portfolio_id", "asset_class")
        .agg(F.sum("market_value").alias("total_mv"))
        .orderBy(F.col("total_mv").desc())
    )

    if report_df.isEmpty():
        logger.warning("No positions found between %s and %s", start_date, end_date)
        return report_df

    # Write to a secured Delta table — not a plain CSV file
    (
        report_df.write
        .format("delta")
        .mode("overwrite")
        .save("/mnt/gold/risk_report")
    )

    return report_df


# ── Utilities ─────────────────────────────────────────────────────────────────

def mount_storage() -> None:
    """Mount Azure Data Lake Storage using a secret-backed service principal."""
    secrets = get_secrets()

    # Check if already mounted to avoid duplicate mount error
    already_mounted = any(
        m.mountPoint == "/mnt/portfolios"
        for m in dbutils.fs.mounts()
    )

    if not already_mounted:
        dbutils.fs.mount(
            source="wasbs://portfolios@aimcoadls.blob.core.windows.net",
            mount_point="/mnt/portfolios",
            extra_configs={
                # Key fetched from Key Vault — never stored in code
                "fs.azure.account.key.aimcoadls.blob.core.windows.net": secrets["storage_key"]
            }
        )
        logger.info("Mounted /mnt/portfolios")
    else:
        logger.info("/mnt/portfolios already mounted — skipping")


def log_pipeline_run(pipeline_name: str, status: str, row_count: int = 0) -> None:
    """Log pipeline execution metadata to the audit Delta table."""
    log_entry = spark.createDataFrame([{
        "pipeline_name": pipeline_name,
        "status": status,
        "row_count": row_count,
        "run_timestamp": str(F.current_timestamp()),
    }])

    log_entry.write.format("delta").mode("append").save("/mnt/gold/pipeline_audit_log")
    logger.info("Pipeline '%s' completed: status=%s rows=%d", pipeline_name, status, row_count)
    # Note: no credentials or connection strings are logged anywhere


# ── Orchestrator: run the full pipeline ──────────────────────────────────────

def run_full_pipeline(trade_file_path: str, start_date: str, end_date: str) -> None:
    """
    Runs Bronze → Silver → Gold in sequence.
    Each stage logs its result; failures stop the pipeline with a clear message.
    """
    try:
        mount_storage()

        logger.info("Starting Bronze ingest...")
        row_count = ingest_trades_bronze(trade_file_path)
        log_pipeline_run("bronze_ingest", "success", row_count)

        logger.info("Starting positions ingest...")
        ingest_positions_jdbc()
        log_pipeline_run("positions_ingest", "success")

        logger.info("Starting Silver cleaning...")
        clean_trades_silver()
        log_pipeline_run("silver_clean", "success")

        logger.info("Starting Gold aggregations...")
        calculate_daily_pnl()
        generate_risk_report(start_date, end_date)
        log_pipeline_run("gold_aggregate", "success")

        logger.info("Pipeline complete.")

    except Exception as exc:
        log_pipeline_run("full_pipeline", f"failed: {exc}")
        raise
