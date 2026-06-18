# sample5_databricks_errors.py
# Databricks notebook — ETL pipeline for investment portfolio data.
# INTENTIONALLY BUGGY — use as: python main.py sample_code/sample5_databricks_errors.py
#
# Simulates a real AIMCo-style workflow:
#   Bronze (raw ingest) → Silver (cleaned) → Gold (aggregated for reporting)

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType
import pandas as pd
from datetime import datetime

spark = SparkSession.builder.appName("PortfolioETL").getOrCreate()

# ── Security: Hardcoded credentials ──────────────────────────────────────────
STORAGE_ACCOUNT_KEY = "xK9mP2lN8qRv4wJzYcBuHdAeGfTsVoXiMnOkPlQr=="
JDBC_PASSWORD       = "aimco_prod_db_2024!"
JDBC_URL            = "jdbc:sqlserver://aimco-prod.database.windows.net:1433;" \
                      "database=PortfolioDB;user=admin;password=aimco_prod_db_2024!"


# ── Bronze Layer: Raw Ingest ──────────────────────────────────────────────────

def ingest_trades_bronze(file_path: str):
    """Read raw trade files from ADLS into the Bronze Delta table."""

    # Bug: inferSchema=True in production — Spark scans the entire file to guess types.
    # This is slow and produces wrong types silently (e.g., "0.00" read as String).
    df = spark.read.option("inferSchema", "true").option("header", "true").csv(file_path)

    # Bug: .collect() pulls ALL rows to the driver node.
    # On a 10M-row trade file this will crash with OutOfMemoryError.
    all_rows = df.collect()
    print(f"Loaded {len(all_rows)} rows")

    # Bug: schema never validated — corrupt or missing columns go undetected
    df.write.format("delta").mode("overwrite").save("/mnt/bronze/trades")


def ingest_positions_jdbc():
    """Pull current positions from SQL Server into Bronze."""

    # Security: credentials hardcoded directly in JDBC options
    positions_df = spark.read \
        .format("jdbc") \
        .option("url", JDBC_URL) \
        .option("dbtable", "dbo.Positions") \
        .option("user", "admin") \
        .option("password", JDBC_PASSWORD) \
        .load()

    positions_df.write.format("delta").mode("overwrite").save("/mnt/bronze/positions")


# ── Silver Layer: Clean & Validate ───────────────────────────────────────────

def clean_trades_silver():
    """Read Bronze trades, clean and write to Silver."""

    df = spark.read.format("delta").load("/mnt/bronze/trades")

    # Bug: Python for-loop over Spark rows — defeats the whole point of distributed
    # processing. Should use df.filter() or df.withColumn() instead.
    # This will be catastrophically slow on large datasets.
    cleaned_rows = []
    for row in df.collect():
        if row["trade_amount"] is not None and float(row["trade_amount"]) > 0:
            cleaned_rows.append(row)

    # Bug: converting back to Spark DataFrame via Pandas loses nullability metadata
    # and forces all data through the driver — not scalable.
    cleaned_df = spark.createDataFrame(pd.DataFrame(cleaned_rows))

    cleaned_df.write.format("delta").mode("overwrite").save("/mnt/silver/trades")


def enrich_with_benchmarks(portfolio_id: str):
    """Join portfolio returns with benchmark data via dynamic SQL."""

    # Security: portfolio_id is interpolated directly — SQL injection risk.
    # An attacker can pass portfolio_id = "' OR '1'='1" to leak all portfolios.
    query = f"""
        SELECT p.*, b.benchmark_return
        FROM portfolio_returns p
        JOIN benchmarks b ON p.asset_class = b.asset_class
        WHERE p.portfolio_id = '{portfolio_id}'
    """
    df = spark.sql(query)
    return df


# ── Gold Layer: Aggregations for Reporting ───────────────────────────────────

def calculate_daily_pnl():
    """Aggregate daily P&L per portfolio and asset class."""

    df = spark.read.format("delta").load("/mnt/silver/trades")

    # Bug: DataFrame is used 3 times below but never cached.
    # Spark re-reads and re-computes it from scratch each time — 3x the I/O.

    total_pnl = df.groupBy("portfolio_id").agg(F.sum("pnl").alias("total_pnl"))
    by_asset  = df.groupBy("portfolio_id", "asset_class").agg(F.sum("pnl").alias("pnl"))
    trade_count = df.groupBy("portfolio_id").agg(F.count("trade_id").alias("num_trades"))

    # Bug: no error handling — if the Delta table is missing or corrupt, this
    # crashes the entire notebook with no useful message.
    total_pnl.write.format("delta").mode("overwrite").save("/mnt/gold/daily_pnl")
    by_asset.write.format("delta").mode("overwrite").save("/mnt/gold/pnl_by_asset")
    trade_count.write.format("delta").mode("overwrite").save("/mnt/gold/trade_count")


def generate_risk_report(start_date: str, end_date: str):
    """Calculate VaR and concentration metrics for the risk team."""

    # Security: date strings injected directly into SQL
    df = spark.sql(f"""
        SELECT portfolio_id, asset_class, SUM(market_value) as total_mv
        FROM silver_positions
        WHERE as_of_date BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY portfolio_id, asset_class
    """)

    # Bug: .toPandas() on a potentially huge DataFrame — pulls everything to driver
    pdf = df.toPandas()

    # Bug: no guard against empty DataFrame — .iloc[0] raises IndexError
    top_holding = pdf.sort_values("total_mv", ascending=False).iloc[0]

    # Security: writes sensitive portfolio data to an unencrypted local file
    pdf.to_csv("/tmp/risk_report.csv", index=False)

    return pdf


# ── Utilities ─────────────────────────────────────────────────────────────────

def mount_storage():
    """Mount Azure Data Lake Storage container."""

    # Security: storage account key hardcoded — should use dbutils.secrets
    dbutils.fs.mount(
        source="wasbs://portfolios@aimcoadls.blob.core.windows.net",
        mount_point="/mnt/portfolios",
        extra_configs={
            "fs.azure.account.key.aimcoadls.blob.core.windows.net": STORAGE_ACCOUNT_KEY
        }
    )


def log_pipeline_run(pipeline_name: str, status: str):
    """Log pipeline execution metadata."""

    conn_str = f"Server=aimco-prod.database.windows.net;Database=Logs;" \
               f"Uid=admin;Pwd={JDBC_PASSWORD}"

    # Security: full connection string (with password) written to Spark event log
    spark.sparkContext.setLocalProperty("pipeline.conn", conn_str)
    print(f"Pipeline '{pipeline_name}' finished with status: {status}")
    print(f"Connection used: {conn_str}")  # Security: password printed to notebook output
