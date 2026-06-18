# sample7_website_errors.py
# Flask web app — investment portfolio dashboard.
# INTENTIONALLY BUGGY — use as: python main.py sample_code/sample7_website_errors.py
#
# Covers: XSS, SQL injection, CSRF, insecure file upload, broken auth, and more.

from flask import Flask, request, render_template_string, redirect, session, jsonify
import sqlite3
import os
import pickle
import hashlib

app = Flask(__name__)

# Security: hardcoded secret key checked into source control
app.secret_key = "aimco_secret_key_2024"

# Security: debug=True in production exposes the interactive debugger to anyone
app.config["DEBUG"] = True

# Security: session cookies not secured
app.config["SESSION_COOKIE_HTTPONLY"] = False
app.config["SESSION_COOKIE_SECURE"]   = False


# ── Authentication ─────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    # Security: MD5 is cryptographically broken — trivially reversible via rainbow tables
    return hashlib.md5(password.encode()).hexdigest()


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    # Security: SQL injection — attacker can log in as any user with:
    # username = "admin'--"  (password check bypassed entirely)
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{hash_password(password)}'"
    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()

    if user:
        session["user_id"]  = user[0]
        session["username"] = user[1]
        session["role"]     = user[3]
        return redirect("/dashboard")

    return "Login failed", 401


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]
    email    = request.form["email"]

    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()

    # Security: SQL injection on all three fields
    cursor.execute(
        f"INSERT INTO users (username, password, email) "
        f"VALUES ('{username}', '{hash_password(password)}', '{email}')"
    )
    conn.commit()
    conn.close()

    return redirect("/login")


# ── Portfolio Dashboard ────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    # Bug: no authentication check — any unauthenticated user can access this
    user_id = session.get("user_id")

    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    # Security: SQL injection via user_id from session
    cursor.execute(f"SELECT * FROM portfolios WHERE user_id = {user_id}")
    portfolios = cursor.fetchall()
    conn.close()

    # Security: XSS — user-controlled data rendered directly into HTML with no escaping.
    # If a portfolio name contains <script>alert(1)</script> it executes in the browser.
    html = "<h1>My Portfolios</h1><ul>"
    for p in portfolios:
        html += f"<li>{p[1]}: ${p[2]}</li>"   # p[1] is portfolio name from DB — unescaped!
    html += "</ul>"

    return render_template_string(html)


@app.route("/search")
def search():
    # Security: search term reflected directly into HTML response — stored XSS
    term = request.args.get("q", "")
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    # Security: SQL injection via query parameter
    cursor.execute(f"SELECT * FROM holdings WHERE ticker LIKE '%{term}%'")
    results = cursor.fetchall()
    conn.close()

    # Security: term rendered without escaping — reflected XSS
    return f"<h2>Results for: {term}</h2>" + str(results)


# ── Trade Submission ───────────────────────────────────────────────────────────

@app.route("/trade", methods=["POST"])
def submit_trade():
    # Security: no CSRF protection — any website can forge a trade request
    # on behalf of a logged-in user by submitting a hidden form to this endpoint.
    ticker   = request.form["ticker"]
    quantity = request.form["quantity"]
    action   = request.form["action"]
    user_id  = session.get("user_id")

    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    # Security: SQL injection on all fields
    cursor.execute(
        f"INSERT INTO trades (user_id, ticker, quantity, action) "
        f"VALUES ({user_id}, '{ticker}', {quantity}, '{action}')"
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "trade submitted"})


# ── File Upload ────────────────────────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload_file():
    # Bug: no authentication check — anyone can upload
    f = request.files["file"]

    # Security: no file extension or MIME type validation.
    # An attacker can upload a .py or .sh file and execute it on the server.
    upload_path = os.path.join("/uploads", f.filename)

    # Security: path traversal — filename="../../../etc/cron.d/backdoor" would
    # overwrite a system file.
    f.save(upload_path)

    return f"Uploaded: {f.filename}"


# ── Admin Panel ────────────────────────────────────────────────────────────────

@app.route("/admin/users")
def admin_users():
    # Bug: no role check — any logged-in user (or unauthenticated user) can
    # view and delete all user accounts.
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, password FROM users")  # Security: returns passwords!
    users = cursor.fetchall()
    conn.close()
    return jsonify(users)


@app.route("/admin/delete_user")
def delete_user():
    # Bug: GET request used for a destructive action — can be triggered by a
    # <img src="/admin/delete_user?id=1"> tag on any page (CSRF via URL).
    user_id = request.args.get("id")
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    # Security: SQL injection
    cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
    conn.commit()
    conn.close()
    return "User deleted"


# ── Session Handling ───────────────────────────────────────────────────────────

@app.route("/save_preferences", methods=["POST"])
def save_preferences():
    data = request.form["preferences"]
    # Security: deserializing user-controlled data with pickle is a remote code
    # execution vulnerability — pickle.loads() executes arbitrary Python code.
    prefs = pickle.loads(data.encode("latin-1"))
    session["preferences"] = prefs
    return "Saved"


if __name__ == "__main__":
    # Security: running with debug=True and host="0.0.0.0" exposes the
    # interactive debugger to the entire network.
    app.run(debug=True, host="0.0.0.0", port=5000)
