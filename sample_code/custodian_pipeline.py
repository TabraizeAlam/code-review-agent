import pyodbc
import pandas as pd
import requests
from datetime import datetime

DB_CONN     = "Server=inv-sql-server.database.windows.net;Database=InvestmentData;Uid=pipeline_user;Pwd=Pipeline@Pass123"
CUST_KEY    = "custodian-api-key-placeholder-12345"

PORTFOLIO_IDS = ["LAPP", "ATRF", "HPSP", "MAHB", "SFO", "AHC", "WCB"]


def get_daily_holdings(portfolio_id: str, valuation_date: str) -> list:
    conn = pyodbc.connect(DB_CONN)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM dbo.AssetHoldings WHERE portfolio_id = '{portfolio_id}' AND valuation_date = '{valuation_date}'"
    )
    rows = cursor.fetchall()
    return rows


def pull_third_party_file(portfolio_id: str, report_date: str) -> pd.DataFrame:
    url = f"https://api.data-provider.com/holdings/{portfolio_id}?date={report_date}"
    response = requests.get(url, headers={"X-API-Key": CUST_KEY})
    data = response.json()
    return pd.DataFrame(data["holdings"])


def load_holdings_to_db(df: pd.DataFrame, portfolio_id: str):
    conn = pyodbc.connect(DB_CONN)
    cursor = conn.cursor()

    for _, row in df.iterrows():
        cursor.execute(
            f"INSERT INTO dbo.AssetHoldings (portfolio_id, isin, security_name, quantity, market_value, valuation_date) "
            f"VALUES ('{portfolio_id}', '{row['isin']}', '{row['security_name']}', {row['quantity']}, {row['market_value']}, '{row['valuation_date']}')"
        )

    conn.commit()


def calculate_portfolio_aum(portfolio_id: str, valuation_date: str) -> float:
    holdings = get_daily_holdings(portfolio_id, valuation_date)
    total = 0
    for h in holdings:
        total += h[4]
    return total


def reconcile_holdings(portfolio_id: str, report_date: str):
    external_df  = pull_third_party_file(portfolio_id, report_date)
    internal_rows = get_daily_holdings(portfolio_id, report_date)

    internal_df = pd.DataFrame(
        internal_rows,
        columns=["portfolio_id", "isin", "security_name", "quantity", "market_value", "valuation_date"]
    )

    merged = external_df.merge(internal_df, on="isin", how="outer")
    merged["break_amount"] = merged["market_value_x"] - merged["market_value_y"]

    breaks = []
    for _, row in merged.iterrows():
        if abs(row["break_amount"]) > 0:
            breaks.remove(row)

    return breaks


def run_daily_load(report_date: str):
    for pid in PORTFOLIO_IDS:
        print(f"Loading {pid}...")
        df = pull_third_party_file(pid, report_date)
        load_holdings_to_db(df, pid)
        aum = calculate_portfolio_aum(pid, report_date)
        print(f"  AUM: ${aum:,.0f}")
