# sample8_website_working.py
# Flask web app — investment portfolio dashboard.
# CLEAN VERSION — production-ready security patterns.
#
# Same routes as sample7 but done correctly.

from flask import Flask, request, render_template, redirect, session, jsonify, abort
from flask_wtf import CSRFProtect
from functools import wraps
import sqlite3
import os
import secrets
import bcrypt
import logging
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Secret key loaded from environment — never hardcoded in source
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Session cookies locked down
app.config["SESSION_COOKIE_HTTPONLY"] = True    # JS cannot read the cookie
app.config["SESSION_COOKIE_SECURE"]   = True    # HTTPS only
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Blocks cross-site cookie sending
app.config["DEBUG"] = False                     # Never True in production

# CSRF protection — applied to every state-changing form automatically
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {"csv", "xlsx", "pdf"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB upload limit
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_db():
    """Return a database connection with Row factory for dict-style access."""
    conn = sqlite3.connect("portfolio.db")
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    """Decorator: redirects unauthenticated requests to /login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: returns 403 if the logged-in user is not an admin."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename: str) -> bool:
    """Return True only if the file has an allowed extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ── Authentication ─────────────────────────────────────────────────────────────

def hash_password(password: str) -> bytes:
    # bcrypt: slow by design, salted automatically, resistant to rainbow tables
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def check_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    with get_db() as conn:
        # Parameterized query — username is a bound value, never part of SQL text
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    # Validate password even on miss (constant-time check prevents user enumeration)
    dummy_hash = bcrypt.hashpw(b"x", bcrypt.gensalt())
    valid = check_password(password, user["password_hash"] if user else dummy_hash)

    if not user or not valid:
        return "Invalid credentials", 401

    # Regenerate session ID on login to prevent session fixation
    session.clear()
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["role"]     = user["role"]

    return redirect("/dashboard")


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]
    email    = request.form["email"]

    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            (username, hash_password(password), email),
        )

    return redirect("/login")


# ── Portfolio Dashboard ────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required                         # Enforces authentication
def dashboard():
    user_id = session["user_id"]

    with get_db() as conn:
        portfolios = conn.execute(
            "SELECT * FROM portfolios WHERE user_id = ?",
            (user_id,),                 # Parameterized — no injection possible
        ).fetchall()

    # render_template uses Jinja2, which auto-escapes all variables by default.
    # Even if a portfolio name contains <script>...</script>, it renders as text.
    return render_template("dashboard.html", portfolios=portfolios)


@app.route("/search")
@login_required
def search():
    term = request.args.get("q", "").strip()

    with get_db() as conn:
        # LIKE with parameterized wildcard — safe from injection
        results = conn.execute(
            "SELECT ticker, name, market_value FROM holdings WHERE ticker LIKE ?",
            (f"%{term}%",),
        ).fetchall()

    # Pass to template — Jinja2 escapes `term` automatically, no XSS
    return render_template("search.html", term=term, results=results)


# ── Trade Submission ───────────────────────────────────────────────────────────

@app.route("/trade", methods=["POST"])
@login_required
# CSRF token is checked automatically by Flask-WTF on every POST
def submit_trade():
    ticker   = request.form["ticker"]
    action   = request.form["action"]
    user_id  = session["user_id"]

    # Validate action before touching the database
    if action not in ("BUY", "SELL"):
        return jsonify({"error": "Invalid action"}), 400

    try:
        quantity = float(request.form["quantity"])
        if quantity <= 0:
            return jsonify({"error": "Quantity must be positive"}), 400
    except ValueError:
        return jsonify({"error": "Quantity must be a number"}), 400

    with get_db() as conn:
        conn.execute(
            "INSERT INTO trades (user_id, ticker, quantity, action) VALUES (?, ?, ?, ?)",
            (user_id, ticker, quantity, action),
        )

    return jsonify({"status": "trade submitted"})


# ── File Upload ────────────────────────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return "No file provided", 400

    f = request.files["file"]

    if not f.filename:
        return "No file selected", 400

    # Whitelist extension check — rejects .py, .sh, .exe, etc.
    if not allowed_file(f.filename):
        return f"File type not allowed. Permitted: {ALLOWED_EXTENSIONS}", 400

    # secure_filename() strips path separators — prevents directory traversal
    safe_name = secure_filename(f.filename)

    # Prefix with a random token so two users can't overwrite each other's files
    final_name  = f"{secrets.token_hex(8)}_{safe_name}"
    upload_path = os.path.join(app.config["UPLOAD_FOLDER"], final_name)

    f.save(upload_path)
    logger.info("User %s uploaded %s", session["user_id"], final_name)

    return jsonify({"uploaded": final_name})


# ── Admin Panel ────────────────────────────────────────────────────────────────

@app.route("/admin/users")
@admin_required                         # Enforces login + admin role
def admin_users():
    with get_db() as conn:
        # Never return password hashes to the client
        users = conn.execute("SELECT id, username, email, role FROM users").fetchall()

    return jsonify([dict(u) for u in users])


@app.route("/admin/delete_user", methods=["POST"])   # POST, not GET — can't be CSRF'd via <img>
@admin_required
def delete_user():
    try:
        user_id = int(request.form["user_id"])
    except (KeyError, ValueError):
        return jsonify({"error": "Invalid user_id"}), 400

    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    logger.info("Admin %s deleted user %s", session["username"], user_id)
    return jsonify({"status": "deleted"})


if __name__ == "__main__":
    # Host bound to localhost only; debug off; secret from env
    app.run(debug=False, host="127.0.0.1", port=5000)
