"""
state.py — Defines what the agent remembers as it runs.

In LangGraph, every node reads from and writes to this shared state.
Think of it as a shared notepad that all agents can read and update.
"""
from typing import TypedDict, List


class Finding(TypedDict):
    """A single issue discovered by one of the review agents."""
    severity: str     # "HIGH", "MEDIUM", or "LOW"
    description: str  # What the problem is
    suggestion: str   # How to fix it


class ReviewState(TypedDict):
    """
    The full state of one code review session.

    LangGraph passes this between nodes. Each agent adds its own findings.
    By the end, all fields are filled and the final_report is ready.
    """
    # --- Input (set at the start, never changed) ---
    code: str        # The code being reviewed
    filename: str    # Name of the file (used in the report title)

    # --- Findings (each agent fills in its own section) ---
    bug_findings: List[Finding]       # From Bug Review Agent
    security_findings: List[Finding]  # From Security Review Agent
    test_findings: List[Finding]      # From Test Coverage Agent

    # --- Output (set by the Orchestrator) ---
    final_report: str   # The combined Markdown report

    # --- Human-in-the-loop (set after human reviews) ---
    human_feedback: str  # "approved" or written feedback from the human
