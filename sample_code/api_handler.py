# sample3_api_handler.py
# A simple REST API request handler — security and robustness issues.
# Use this as: python main.py sample_code/sample3_api_handler.py

import os
import requests

# Security: hardcoded API key in source code
PAYMENT_API_KEY = "pk_live_abc123secret"
INTERNAL_TOKEN = "Bearer eyJhbGciOiJIUzI1NiJ9.secret"


def fetch_user_profile(user_id):
    """Fetch user profile from internal API."""
    # Security: no authentication on the request
    url = f"https://api.internal.com/users/{user_id}"
    response = requests.get(url)
    # Bug: no check for response.status_code — will crash on 404 or 500
    return response.json()


def charge_customer(customer_id, amount_dollars):
    """Charge a customer using the payment API."""
    # Bug: no input validation — what if amount_dollars is negative or zero?
    payload = {
        "customer_id": customer_id,
        "amount": int(amount_dollars * 100),  # Bug: float * 100 can lose precision (e.g., 1.15 * 100 = 114.99999)
        "currency": "usd",
    }
    response = requests.post(
        "https://api.payment.com/charge",
        json=payload,
        headers={"Authorization": f"Bearer {PAYMENT_API_KEY}"},  # Security: key in source
    )
    return response.json()


def search_products(query):
    """Search the product catalog."""
    # Security: query passed to a shell command — command injection!
    import subprocess
    result = subprocess.run(f"grep -r '{query}' /data/catalog/", shell=True, capture_output=True)
    return result.stdout.decode()


def log_request(user_id, action, password=None):
    """Log a user action for audit purposes."""
    # Security: password may be logged in plaintext to a file
    print(f"[AUDIT] user={user_id} action={action} password={password}")
    with open("audit.log", "a") as f:
        f.write(f"user={user_id} action={action} password={password}\n")
