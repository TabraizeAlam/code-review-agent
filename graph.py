from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from state import ReviewState
from agents import bug_review_agent, security_review_agent, test_review_agent, orchestrator_agent


def human_review_node(state: ReviewState) -> dict:
    human_feedback = interrupt("Review the report and approve or provide feedback.")
    return {"human_feedback": human_feedback}


def build_graph():
    workflow = StateGraph(ReviewState)

    workflow.add_node("bug_review", bug_review_agent)
    workflow.add_node("security_review", security_review_agent)
    workflow.add_node("test_review", test_review_agent)
    workflow.add_node("orchestrate", orchestrator_agent)
    workflow.add_node("human_review", human_review_node)

    workflow.add_edge(START, "bug_review")
    workflow.add_edge("bug_review", "security_review")
    workflow.add_edge("security_review", "test_review")
    workflow.add_edge("test_review", "orchestrate")
    workflow.add_edge("orchestrate", "human_review")
    workflow.add_edge("human_review", END)

    return workflow.compile(checkpointer=MemorySaver())
