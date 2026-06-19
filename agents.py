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


def get_llm():
    return ChatOpenAI(
        model=os.getenv("NEBIUS_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        base_url="https://api.studio.nebius.com/v1/",
        api_key=os.getenv("NEBIUS_API_KEY"),
        temperature=0,
    )


def parse_json_findings(text: str) -> list:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return []


def format_findings_text(findings: list, label: str) -> str:
    if not findings:
        return f"{label}: No issues found.\n"
    lines = [f"{label} — {len(findings)} issue(s):"]
    for i, f in enumerate(findings, 1):
        lines.append(f"  {i}. [{f.get('severity', '?')}] {f.get('description', '')}")
        lines.append(f"     Fix: {f.get('suggestion', '')}")
    return "\n".join(lines)


def bug_review_agent(state: ReviewState) -> dict:
    print("\n[Bug Agent] Scanning for bugs and anti-patterns...")
    llm = get_llm()
    try:
        response = llm.invoke([
            SystemMessage(content=BUG_AGENT_PROMPT),
            HumanMessage(content=f"Review this code:\n\n```python\n{state['code']}\n```"),
        ])
        findings = parse_json_findings(response.content)
        print(f"  {len(findings)} issue(s) found")
    except Exception as e:
        print(f"  Error: {e}")
        findings = []
    return {"bug_findings": findings}


def security_review_agent(state: ReviewState) -> dict:
    print("\n[Security Agent] Scanning for vulnerabilities...")
    llm = get_llm()
    try:
        response = llm.invoke([
            SystemMessage(content=SECURITY_AGENT_PROMPT),
            HumanMessage(content=f"Review this code:\n\n```python\n{state['code']}\n```"),
        ])
        findings = parse_json_findings(response.content)
        print(f"  {len(findings)} issue(s) found")
    except Exception as e:
        print(f"  Error: {e}")
        findings = []
    return {"security_findings": findings}


def test_review_agent(state: ReviewState) -> dict:
    print("\n[Test Agent] Checking test coverage gaps...")
    llm = get_llm()
    try:
        response = llm.invoke([
            SystemMessage(content=TEST_AGENT_PROMPT),
            HumanMessage(content=f"Review this code:\n\n```python\n{state['code']}\n```"),
        ])
        findings = parse_json_findings(response.content)
        print(f"  {len(findings)} gap(s) found")
    except Exception as e:
        print(f"  Error: {e}")
        findings = []
    return {"test_findings": findings}


def orchestrator_agent(state: ReviewState) -> dict:
    print("\n[Orchestrator] Compiling final report...")
    llm = get_llm()

    all_findings = "\n\n".join([
        format_findings_text(state["bug_findings"], "BUG FINDINGS"),
        format_findings_text(state["security_findings"], "SECURITY FINDINGS"),
        format_findings_text(state["test_findings"], "TEST COVERAGE FINDINGS"),
    ])

    try:
        response = llm.invoke([
            SystemMessage(content=ORCHESTRATOR_PROMPT.format(filename=state["filename"])),
            HumanMessage(content=all_findings),
        ])
        report = response.content
        print("  Done")
    except Exception as e:
        print(f"  Error: {e}")
        report = f"# Code Review: {state['filename']}\n\n{all_findings}"

    return {"final_report": report}
