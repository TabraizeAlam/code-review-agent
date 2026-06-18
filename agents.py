"""
agents.py — The four agents in the pipeline.

Each agent is a plain Python function that:
  1. Reads from the shared ReviewState
  2. Calls the LLM with a focused prompt
  3. Returns a dict with ONLY the fields it updated

LangGraph merges each returned dict back into the shared state automatically.
"""
import os
import json
import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from state import ReviewState
from prompts import (
    BUG_AGENT_PROMPT,
    SECURITY_AGENT_PROMPT,
    TEST_AGENT_PROMPT,
    ORCHESTRATOR_PROMPT,
)


def get_llm() -> ChatOpenAI:
    """
    Creates the LLM client pointed at Nebius.

    Nebius uses an OpenAI-compatible API, so we can use ChatOpenAI
    and just swap the base_url and api_key.
    temperature=0 means deterministic output — better for analysis tasks.
    """
    return ChatOpenAI(
        model=os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct"),
        base_url="https://api.studio.nebius.com/v1/",
        api_key=os.getenv("NEBIUS_API_KEY"),
        temperature=0,
    )


def parse_json_findings(response_text: str) -> list:
    """
    Safely extract a JSON array from LLM response text.

    LLMs sometimes add preamble like "Here are my findings:" before
    the JSON. This function searches for the array regardless.

    Error handling: if parsing fails completely, returns [] so the
    pipeline can continue rather than crashing.
    """
    text = response_text.strip()

    # 1. Try direct parse (ideal case — LLM returned only JSON)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # 2. Search for [...] block anywhere in the response
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # 3. Nothing parseable found
    return []


def format_findings_text(findings: list, label: str) -> str:
    """Format findings list into readable text for the orchestrator prompt."""
    if not findings:
        return f"{label}: No issues found.\n"

    lines = [f"{label} — {len(findings)} issue(s):"]
    for i, f in enumerate(findings, 1):
        lines.append(f"  {i}. [{f.get('severity', '?')}] {f.get('description', '')}")
        lines.append(f"     Fix: {f.get('suggestion', '')}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Agent 1: Bug Review
# ─────────────────────────────────────────────

def bug_review_agent(state: ReviewState) -> dict:
    """
    Analyzes code for bugs and anti-patterns.

    This is a LangGraph node — it receives the full state and
    returns only the field(s) it changed: bug_findings.
    """
    print("\n[Bug Agent] Analyzing for bugs and anti-patterns...")

    llm = get_llm()

    try:
        response = llm.invoke([
            SystemMessage(content=BUG_AGENT_PROMPT),
            HumanMessage(content=f"Analyze this code:\n\n```python\n{state['code']}\n```"),
        ])
        findings = parse_json_findings(response.content)
        print(f"  → {len(findings)} bug/anti-pattern issue(s) found")

    except Exception as e:
        # Never crash the pipeline — log and continue with empty findings
        print(f"  → Error calling LLM: {e}. Continuing with no findings.")
        findings = []

    return {"bug_findings": findings}


# ─────────────────────────────────────────────
# Agent 2: Security Review
# ─────────────────────────────────────────────

def security_review_agent(state: ReviewState) -> dict:
    """
    Scans code for security vulnerabilities.

    Runs after bug_review — state already has bug_findings,
    but this agent ignores them and focuses only on security.
    """
    print("\n[Security Agent] Scanning for security vulnerabilities...")

    llm = get_llm()

    try:
        response = llm.invoke([
            SystemMessage(content=SECURITY_AGENT_PROMPT),
            HumanMessage(content=f"Analyze this code:\n\n```python\n{state['code']}\n```"),
        ])
        findings = parse_json_findings(response.content)
        print(f"  → {len(findings)} security issue(s) found")

    except Exception as e:
        print(f"  → Error calling LLM: {e}. Continuing with no findings.")
        findings = []

    return {"security_findings": findings}


# ─────────────────────────────────────────────
# Agent 3: Test Coverage Review
# ─────────────────────────────────────────────

def test_review_agent(state: ReviewState) -> dict:
    """
    Identifies missing tests and test coverage gaps.

    Runs after security_review. By now state has both
    bug_findings and security_findings, but this agent
    only cares about testing gaps.
    """
    print("\n[Test Agent] Evaluating test coverage gaps...")

    llm = get_llm()

    try:
        response = llm.invoke([
            SystemMessage(content=TEST_AGENT_PROMPT),
            HumanMessage(content=f"Analyze this code:\n\n```python\n{state['code']}\n```"),
        ])
        findings = parse_json_findings(response.content)
        print(f"  → {len(findings)} test gap(s) found")

    except Exception as e:
        print(f"  → Error calling LLM: {e}. Continuing with no findings.")
        findings = []

    return {"test_findings": findings}


# ─────────────────────────────────────────────
# Orchestrator: Combines all findings
# ─────────────────────────────────────────────

def orchestrator_agent(state: ReviewState) -> dict:
    """
    Reads findings from all three agents and writes a final report.

    This is the 'manager' agent — it doesn't analyze code itself.
    It just takes all the specialized findings and formats them
    into one clear, prioritized Markdown report.
    """
    print("\n[Orchestrator] Compiling final review report...")

    llm = get_llm()

    # Build a text summary of all findings to give to the orchestrator
    all_findings_text = "\n\n".join([
        format_findings_text(state["bug_findings"], "BUG FINDINGS"),
        format_findings_text(state["security_findings"], "SECURITY FINDINGS"),
        format_findings_text(state["test_findings"], "TEST COVERAGE FINDINGS"),
    ])

    try:
        response = llm.invoke([
            SystemMessage(content=ORCHESTRATOR_PROMPT.format(filename=state["filename"])),
            HumanMessage(content=all_findings_text),
        ])
        report = response.content
        print("  → Report compiled successfully")

    except Exception as e:
        print(f"  → Error calling LLM: {e}. Using raw findings as fallback report.")
        report = f"# Code Review: {state['filename']}\n\n{all_findings_text}"

    return {"final_report": report}
