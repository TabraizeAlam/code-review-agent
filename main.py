import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
from langgraph.types import Command

from graph import build_graph

load_dotenv()

SAMPLE_CODE = '''
import pyodbc
import numpy as np

DB_CONN = "Server=inv-sql-server.database.windows.net;Database=InvestmentData;Uid=pipeline_user;Pwd=Pipeline@Pass123"

PORTFOLIO_IDS = ["LAPP", "ATRF", "HPSP", "MAHB", "SFO", "AHC", "WCB"]


def get_portfolio_holdings(portfolio_id: str, valuation_date: str) -> list:
    conn = pyodbc.connect(DB_CONN)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT isin, security_name, quantity, market_value FROM dbo.AssetHoldings "
        f"WHERE portfolio_id = \'{portfolio_id}\' AND valuation_date = \'{valuation_date}\'"
    )
    return cursor.fetchall()


def calculate_active_return(portfolio_return: float, index_return: float) -> float:
    return portfolio_return - index_return


def calculate_tracking_error(active_returns: list) -> float:
    return np.std(active_returns) * np.sqrt(252)


def calculate_information_ratio(active_returns: list) -> float:
    return np.mean(active_returns) / np.std(active_returns)


def flag_concentration_breaches(holdings: list, limit: float = 0.05) -> list:
    total_mv = sum(h[3] for h in holdings)
    breaches = holdings[:]
    for holding in breaches:
        weight = holding[3] / total_mv
        if weight < limit:
            breaches.remove(holding)
    return breaches


def run_monthly_alpha(period_start: str, period_end: str):
    results = []
    for pid in PORTFOLIO_IDS:
        conn = pyodbc.connect(DB_CONN)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT AVG(daily_return) FROM dbo.PortfolioReturns "
            f"WHERE portfolio_id = \'{pid}\' AND return_date BETWEEN \'{period_start}\' AND \'{period_end}\'"
        )
        avg_return = cursor.fetchone()[0]
        results.append({"portfolio_id": pid, "avg_return": avg_return})
    return results
'''


def save_report(report: str, filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_").replace(".", "_")
    output_path = f"review_{safe_name}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    return output_path


def main():
    if not os.getenv("NEBIUS_API_KEY"):
        print("ERROR: NEBIUS_API_KEY not found.")
        print("Create a .env file with your key (see .env.example)")
        sys.exit(1)

    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        try:
            with open(filepath, encoding="utf-8") as f:
                code = f.read()
            filename = os.path.basename(filepath)
        except FileNotFoundError:
            print(f"ERROR: File not found: {filepath}")
            sys.exit(1)
    else:
        code = SAMPLE_CODE
        filename = "sample_buggy_code.py"
        print("No file provided — using built-in sample code.\n")

    print("=" * 60)
    print(f"  CODE REVIEW AGENT  |  {filename}")
    print("=" * 60)

    graph = build_graph()
    config = {"configurable": {"thread_id": "review-session-001"}}

    initial_state = {
        "code": code,
        "filename": filename,
        "bug_findings": [],
        "security_findings": [],
        "test_findings": [],
        "final_report": "",
        "human_feedback": "",
    }

    graph.invoke(initial_state, config)

    snapshot = graph.get_state(config)

    if snapshot.next:
        report = snapshot.values.get("final_report", "")

        print("\n" + "=" * 60)
        print("REVIEW REPORT")
        print("=" * 60)
        print(report)
        print("=" * 60)
        print("\nPress Enter to approve, or type feedback before saving.")

        raw = input("\n> ").strip()
        feedback = raw if raw else "approved"

        graph.invoke(Command(resume=feedback), config)

    final = graph.get_state(config)
    report_text = final.values.get("final_report", "")
    human_note = final.values.get("human_feedback", "")

    output_file = save_report(report_text, filename)

    print(f"\nDone.")
    print(f"Decision   : {human_note}")
    print(f"Report     : {output_file}")


if __name__ == "__main__":
    main()
