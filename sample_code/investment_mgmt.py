# sample4_investment_mgmt.py
# Investment Management System — portfolio tracking, trade execution, reporting.
# Use this as: python main.py sample_code/sample4_investment_mgmt.py

import sqlite3
import requests
from datetime import datetime

# ── Security: Hardcoded credentials ──────────────────────────────────────────
DB_PASSWORD      = "aimco_db_pass_2024"
BLOOMBERG_API_KEY = "BBG-LIVE-abc123secret"
CUSTODIAN_TOKEN  = "Bearer eyJhbGciOiJIUzI1NiJ9.custodian_secret"


# ── Portfolio Management ──────────────────────────────────────────────────────

def get_portfolio(client_id):
    """Fetch a client's full portfolio from the database."""
    conn = sqlite3.connect("investments.db")
    cursor = conn.cursor()

    # Security: SQL injection — client_id goes directly into the query string
    cursor.execute(f"SELECT * FROM portfolios WHERE client_id = '{client_id}'")
    rows = cursor.fetchall()
    # Bug: connection never closed — resource leak on every call

    return rows


def calculate_portfolio_value(holdings: list) -> float:
    """
    Calculate total portfolio value from a list of holdings.
    Each holding is (ticker, quantity, purchase_price).
    """
    total = 0
    for holding in holdings:
        ticker, quantity, purchase_price = holding
        price = get_market_price(ticker)
        # Bug: if get_market_price() returns None (API failure), this crashes with:
        # TypeError: unsupported operand type(s) for *: 'int' and 'NoneType'
        total += quantity * price
    return total


def get_market_price(ticker: str) -> float:
    """Fetch the current market price of a security from Bloomberg."""
    response = requests.get(
        f"https://api.bloomberg.com/price/{ticker}",
        headers={"Authorization": f"Bearer {BLOOMBERG_API_KEY}"}
    )
    # Bug: no status code check — a 404 or 500 will silently return garbage JSON
    data = response.json()
    return data["price"]


# ── Trade Execution ───────────────────────────────────────────────────────────

def execute_trade(client_id, ticker, action, quantity, price):
    """
    Execute a buy or sell order and record it.
    action: 'BUY' or 'SELL'
    """
    # Bug: no validation — what if quantity is negative? price is zero?
    # A negative quantity would silently create an invalid trade record.

    if action not in ("BUY", "SELL"):
        print("Invalid action")
        return  # Bug: returns None instead of raising — caller can't tell it failed

    trade_value = quantity * price

    conn = sqlite3.connect("investments.db")
    cursor = conn.cursor()

    # Security: SQL injection on every field
    cursor.execute(
        f"INSERT INTO trades (client_id, ticker, action, quantity, price, timestamp) "
        f"VALUES ('{client_id}', '{ticker}', '{action}', {quantity}, {price}, '{datetime.now()}')"
    )
    conn.commit()
    # Bug: connection never closed

    # Security: logs the full trade including price to a plain text file
    with open("trade_log.txt", "a") as f:
        f.write(f"client={client_id} ticker={ticker} action={action} qty={quantity} price={price}\n")

    return trade_value


def rebalance_portfolio(client_id, target_weights: dict):
    """
    Rebalance a client portfolio to match target asset weights.
    target_weights: {"AAPL": 0.30, "MSFT": 0.40, "CASH": 0.30}
    """
    holdings = get_portfolio(client_id)
    total_value = calculate_portfolio_value(holdings)

    orders = []
    for ticker, target_weight in target_weights.items():
        target_value = total_value * target_weight
        # Bug: if ticker is not in holdings, current_value will KeyError
        current_value = next(h[2] * h[1] for h in holdings if h[0] == ticker)
        delta = target_value - current_value

        if delta > 0:
            orders.append(("BUY", ticker, delta))
        elif delta < 0:
            orders.append(("SELL", ticker, abs(delta)))

    return orders


# ── Reporting ─────────────────────────────────────────────────────────────────

def generate_performance_report(client_id: str, start_date: str, end_date: str) -> dict:
    """Generate a period performance report for a client."""
    conn = sqlite3.connect("investments.db")
    cursor = conn.cursor()

    # Security: SQL injection on dates
    cursor.execute(
        f"SELECT * FROM trades WHERE client_id = '{client_id}' "
        f"AND timestamp BETWEEN '{start_date}' AND '{end_date}'"
    )
    trades = cursor.fetchall()
    # Bug: connection never closed

    if not trades:
        return {}

    total_bought  = sum(t[4] * t[3] for t in trades if t[2] == "BUY")
    total_sold    = sum(t[4] * t[3] for t in trades if t[2] == "SELL")
    realized_pnl  = total_sold - total_bought

    # Bug: no handling for division by zero when total_bought is 0
    return_pct = (realized_pnl / total_bought) * 100

    return {
        "client_id"  : client_id,
        "period"     : f"{start_date} to {end_date}",
        "total_bought": total_bought,
        "total_sold"  : total_sold,
        "realized_pnl": realized_pnl,
        "return_pct"  : return_pct,
    }


def send_report_to_client(client_id: str, report: dict):
    """Send a performance report to the client via the custodian portal."""
    response = requests.post(
        "https://api.custodian.com/reports/send",
        json={
            "client_id": client_id,
            "report": report,
            # Security: internal API token hardcoded and included in every payload
            "auth_token": CUSTODIAN_TOKEN,
        },
    )
    # Bug: no check on response.status_code — failure is silently ignored
    print(f"Report sent for client {client_id}")


# ── Compliance ────────────────────────────────────────────────────────────────

def check_concentration_limit(holdings: list, limit: float = 0.25) -> list:
    """
    Flag any single position that exceeds the concentration limit.
    Returns a list of (ticker, weight) tuples that breach the limit.
    """
    total = calculate_portfolio_value(holdings)

    # Bug: if total is 0 (empty portfolio), ZeroDivisionError on next line
    weights = [(h[0], (h[1] * h[2]) / total) for h in holdings]

    # Bug: list is mutated while iterating — some breaches may be skipped
    breaches = weights[:]
    for w in breaches:
        if w[1] < limit:
            breaches.remove(w)

    return breaches
