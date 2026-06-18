"""
graph.py — Wires all agents into a LangGraph state machine.

The graph defines the CONTROL FLOW — which agent runs in what order.
This is the core of LangGraph: you describe a graph of nodes and edges,
and LangGraph handles executing it, passing state, and saving checkpoints.

Pipeline:
  START
    ↓
  bug_review        ← Agent 1 analyzes for bugs
    ↓
  security_review   ← Agent 2 scans for vulnerabilities
    ↓
  test_review       ← Agent 3 checks test coverage
    ↓
  orchestrate       ← Orchestrator writes the final report
    ↓
  human_review      ← ⏸ PAUSES HERE — waits for human approval
    ↓
  END
"""
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from state import ReviewState
from agents import (
    bug_review_agent,
    security_review_agent,
    test_review_agent,
    orchestrator_agent,
)


def human_review_node(state: ReviewState) -> dict:
    """
    Human-in-the-loop checkpoint — the agent pauses here.

    LangGraph's `interrupt()` saves the current state and stops execution.
    The main.py caller shows the report to the human, collects feedback,
    then resumes the graph by passing Command(resume=feedback).

    This pattern ensures a human reviews every report before it's saved —
    the project handout calls this a "write action deserving human approval."
    """
    human_feedback = interrupt(
        "Please review the report. Press Enter to approve, or type feedback."
    )
    return {"human_feedback": human_feedback}


def build_graph():
    """
    Builds and compiles the multi-agent review graph.

    Returns a compiled LangGraph app ready to run.

    Key concepts used here:
    - StateGraph: a graph where nodes share typed state
    - add_node: registers a function as a node
    - add_edge: connects nodes (sequential pipeline here)
    - MemorySaver: saves state between invocations (required for interrupt/resume)
    - compile: turns the graph definition into a runnable app
    """
    workflow = StateGraph(ReviewState)

    # Register each agent as a named node
    workflow.add_node("bug_review", bug_review_agent)
    workflow.add_node("security_review", security_review_agent)
    workflow.add_node("test_review", test_review_agent)
    workflow.add_node("orchestrate", orchestrator_agent)
    workflow.add_node("human_review", human_review_node)

    # Wire nodes together in sequence
    workflow.add_edge(START, "bug_review")
    workflow.add_edge("bug_review", "security_review")
    workflow.add_edge("security_review", "test_review")
    workflow.add_edge("test_review", "orchestrate")
    workflow.add_edge("orchestrate", "human_review")
    workflow.add_edge("human_review", END)

    # MemorySaver stores the graph state so we can pause and resume.
    # Without it, interrupt() wouldn't know where to pick up.
    checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)
