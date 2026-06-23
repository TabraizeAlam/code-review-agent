import numpy as np
import pandas as pd
import pyodbc

DB_CONN = "Server=inv-sql-server.database.windows.net;Database=InvestmentData;Uid=perf_user;Pwd=Perf@Pass123"

INDEX_MAP = {
    "FUND_A": "MSCI World (CAD)",
    "FUND_B": "MSCI World (CAD)",
    "FUND_C": "FTSE Canada Universe Bond",
    "FUND_D": "CPI + 4%",
    "FUND_E": "MSCI World (CAD)",
    "FUND_F": "CPI + 4%",
    "FUND_G": "FTSE Canada 91-Day T-Bill",
}


def get_portfolio_returns(portfolio_id: str, start_date: str, end_date: str) -> list:
    conn = pyodbc.connect(DB_CONN)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT return_date, daily_return FROM dbo.PortfolioReturns "
        f"WHERE portfolio_id = '{portfolio_id}' AND return_date BETWEEN '{start_date}' AND '{end_date}'"
    )
    return cursor.fetchall()


def get_index_returns(index_name: str, start_date: str, end_date: str) -> list:
    conn = pyodbc.connect(DB_CONN)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT return_date, daily_return FROM dbo.IndexReturns "
        f"WHERE index_name = '{index_name}' AND return_date BETWEEN '{start_date}' AND '{end_date}'"
    )
    return cursor.fetchall()


def calculate_alpha(portfolio_id: str, start_date: str, end_date: str) -> dict:
    portfolio_rows = get_portfolio_returns(portfolio_id, start_date, end_date)
    index_name     = INDEX_MAP[portfolio_id]
    index_rows     = get_index_returns(index_name, start_date, end_date)

    portfolio_returns = [r[1] for r in portfolio_rows]
    index_returns     = [r[1] for r in index_rows]

    active_returns    = [p - i for p, i in zip(portfolio_returns, index_returns)]
    cumulative_port   = np.prod([1 + r for r in portfolio_returns]) - 1
    cumulative_index  = np.prod([1 + r for r in index_returns]) - 1
    alpha             = cumulative_port - cumulative_index

    tracking_error    = np.std(active_returns) * np.sqrt(252)
    information_ratio = np.mean(active_returns) / np.std(active_returns)

    return {
        "portfolio_id":     portfolio_id,
        "index_name":       index_name,
        "portfolio_return": cumulative_port,
        "index_return":     cumulative_index,
        "alpha_bps":        alpha * 10000,
        "tracking_error":   tracking_error,
        "information_ratio": information_ratio,
    }


def calculate_asset_class_attribution(portfolio_id: str, valuation_date: str) -> pd.DataFrame:
    conn = pyodbc.connect(DB_CONN)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT asset_class, SUM(market_value) as mv, SUM(pnl) as pnl "
        f"FROM dbo.AssetHoldings WHERE portfolio_id = '{portfolio_id}' AND valuation_date = '{valuation_date}' "
        f"GROUP BY asset_class"
    )
    rows = cursor.fetchall()

    df = pd.DataFrame(rows, columns=["asset_class", "market_value", "pnl"])
    total_mv = df["market_value"].sum()

    df["weight"] = df["market_value"] / total_mv
    df["contribution"] = df["weight"] * (df["pnl"] / df["market_value"])

    return df


def run_monthly_attribution(period_start: str, period_end: str):
    results = []
    for pid in INDEX_MAP.keys():
        result = calculate_alpha(pid, period_start, period_end)
        results.append(result)
        print(f"{pid}: Alpha = {result['alpha_bps']:.1f} bps  |  IR = {result['information_ratio']:.2f}")

    summary_df = pd.DataFrame(results)
    summary_df.to_csv(f"/tmp/attribution_{period_end}.csv", index=False)
    return summary_df
