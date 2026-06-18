"""
main.py — Entry point for the Code Review Agent.

How to run:
  python main.py                         # Reviews the built-in sample code
  python main.py path/to/yourfile.py     # Reviews any Python file you provide

What happens:
  1. Three specialized agents analyze the code in sequence
  2. An orchestrator compiles their findings into a report
  3. YOU review the report and approve or give feedback
  4. The report is saved as a Markdown file
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
from langgraph.types import Command

from graph import build_graph

# Load NEBIUS_API_KEY and NEBIUS_MODEL from .env file
load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Sample code for the demo (intentionally full of problems)
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_CODE = '''
import sqlite3
import os

# ---- SECURITY: Hardcoded credentials ----
DB_PASSWORD = "admin123"
API_KEY = "sk-prod-secret-key-abc123"


def get_user(user_id):
    """Fetch a user record from the database."""
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # SECURITY: SQL injection — user_id is pasted directly into the query.
    # An attacker can pass: user_id = "1 OR 1=1 --" to dump all users.
    query = f"SELECT id, username, password, email FROM users WHERE id = {user_id}"
    cursor.execute(query)

    user = cursor.fetchone()
    # BUG: conn.close() is never called — database connection leaks!

    if user:
        # SECURITY: Password returned in plaintext — never expose passwords in responses!
        return {"id": user[0], "username": user[1], "password": user[2]}
    return None


def apply_discount(price, discount_pct):
    """Apply a percentage discount and return the final price."""
    # BUG: No validation — what if price is negative? discount_pct > 100?
    # This silently returns wrong results instead of raising an error.
    discount = price * discount_pct / 100
    return price - discount


def remove_negatives(numbers):
    """Remove all negative numbers from a list in-place."""
    # BUG: Classic Python anti-pattern — modifying a list while iterating it.
    # Python skips elements after each removal, so some negatives are never removed.
    for n in numbers:
        if n < 0:
            numbers.remove(n)
    return numbers


def process_batch(items=[]):
    """Process a batch of items (adds a timestamp to each)."""
    # BUG: Mutable default argument — the [] is created once when the function
    # is defined, not each time it's called. All calls share the same list!
    from datetime import datetime
    items.append(datetime.now())
    return items
'''


def save_report(report: str, filename: str) -> str:
    """Save the review report as a Markdown file and return the output path."""
    # Make the filename safe for the filesystem
    safe_name = filename.replace("/", "_").replace("\\", "_").replace(".", "_")
    output_path = f"review_{safe_name}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    return output_path


def main():
    # ── Pre-flight check ──────────────────────────────────────────────────────
    if not os.getenv("NEBIUS_API_KEY"):
        print("ERROR: NEBIUS_API_KEY not found.")
        print("Steps to fix:")
        print("  1. Copy .env.example to .env")
        print("  2. Open .env and paste your Nebius key")
        print("  3. Run again")
        sys.exit(1)

    # ── Load the code to review ───────────────────────────────────────────────
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        try:
            with open(filepath, encoding="utf-8") as f:
                code = f.read()
            filename = os.path.basename(filepath)
            print(f"Loaded: {filepath}")
        except FileNotFoundError:
            print(f"ERROR: File not found: {filepath}")
            sys.exit(1)
    else:
        code = SAMPLE_CODE
        filename = "sample_buggy_code.py"
        print("No file provided — running with built-in sample code.\n")

    print("=" * 60)
    print("  CODE REVIEW AGENT")
    print(f"  File: {filename}")
    print("=" * 60)
    print("\nPipeline: Bug Agent → Security Agent → Test Agent → Orchestrator → You\n")

    # ── Build the LangGraph app ───────────────────────────────────────────────
    graph = build_graph()

    # thread_id: identifies this review session.
    # LangGraph uses it to save and restore state between the two invoke() calls.
    config = {"configurable": {"thread_id": "review-session-001"}}

    # Initial state — everything starts empty except code and filename
    initial_state = {
        "code": code,
        "filename": filename,
        "bug_findings": [],
        "security_findings": [],
        "test_findings": [],
        "final_report": "",
        "human_feedback": "",
    }

    # ── First run: agents analyze the code ───────────────────────────────────
    # graph.invoke() runs the pipeline until it hits interrupt() in human_review_node.
    # At that point it saves state and returns — it does NOT crash or raise.
    graph.invoke(initial_state, config)

    # ── Human-in-the-loop checkpoint ─────────────────────────────────────────
    snapshot = graph.get_state(config)

    if snapshot.next:
        # The graph is paused — show the report and ask for human decision
        report = snapshot.values.get("final_report", "")

        print("\n" + "=" * 60)
        print("REVIEW REPORT (ready for your approval)")
        print("=" * 60)
        print(report)
        print("=" * 60)

        print("\nOptions:")
        print("  Press Enter            → Approve and save")
        print("  Type feedback + Enter  → Add a note before saving")

        raw = input("\nYour decision: ").strip()
        feedback = raw if raw else "approved"

        # ── Resume the graph ─────────────────────────────────────────────────
        # Command(resume=feedback) passes the value back into interrupt()
        # inside human_review_node, which then returns {"human_feedback": feedback}.
        # The graph continues to END.
        graph.invoke(Command(resume=feedback), config)

    # ── Save the final report ─────────────────────────────────────────────────
    final = graph.get_state(config)
    report_text = final.values.get("final_report", "")
    human_note = final.values.get("human_feedback", "")

    output_file = save_report(report_text, filename)

    print(f"\nDone.")
    print(f"Human decision : {human_note}")
    print(f"Report saved to: {output_file}")


if __name__ == "__main__":
    main()
