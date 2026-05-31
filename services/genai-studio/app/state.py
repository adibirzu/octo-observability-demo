"""Shared state for the AI Studio multi-agent graph."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def merge_token_usage(left: dict, right: dict) -> dict:
    """LangGraph reducer: sum token deltas across agent nodes."""
    left = left or {}
    right = right or {}
    return {
        "input": int(left.get("input", 0)) + int(right.get("input", 0)),
        "output": int(left.get("output", 0)) + int(right.get("output", 0)),
    }

# Agents in execution order. The supervisor advances through these.
AGENT_SEQUENCE: tuple[str, ...] = (
    "sales_analyst",
    "evidence",
    "code_interpreter",
    "product_copy",
    "presenter",
)


class StudioState(TypedDict, total=False):
    """State threaded through the merchandising-brief workflow."""

    # Inputs
    messages: Annotated[list, add_messages]
    request: str  # user instruction, e.g. "merchandising brief for thermal-mapping drones"
    category: str  # optional category focus
    run_id: str
    session_id: str
    user: str

    # Supervisor control
    next_agent: str  # the agent the supervisor routes to next, or "done"
    completed: list[str]  # agents that have run
    step: int

    # Agent outputs
    sales: dict[str, Any]  # Sales Analyst: trend facts from ATP
    evidence: dict[str, Any]  # Evidence/RAG: catalog + external context
    chart: dict[str, Any]  # Code Interpreter: chart artifact + computed table
    copy: dict[str, Any]  # Product Copy: marketing copy
    brief: str  # Presenter: final markdown brief

    # Telemetry / errors
    errors: list[str]
    # Reducer sums per-node deltas (nodes return only their own usage).
    token_usage: Annotated[dict[str, int], merge_token_usage]


def empty_state(**overrides: Any) -> StudioState:
    """Construct an initial state with safe defaults."""
    base: StudioState = {
        "messages": [],
        "request": "",
        "category": "",
        "run_id": "",
        "session_id": "",
        "user": "",
        "next_agent": "sales_analyst",
        "completed": [],
        "step": 0,
        "sales": {},
        "evidence": {},
        "chart": {},
        "copy": {},
        "brief": "",
        "errors": [],
        "token_usage": {"input": 0, "output": 0},
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base
