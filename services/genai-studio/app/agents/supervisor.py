"""Supervisor node — orchestrates the agent sequence and decides when done.

Routing is deterministic (advance through AGENT_SEQUENCE based on ``completed``)
for reliability, but the supervisor makes one LLM call on entry to produce a short
plan so the agentic intent is visible in the trace. Bounded by STUDIO_MAX_STEPS.
"""

from __future__ import annotations

import logging

from app.agents.common import call_llm
from app.config import get_settings
from app.observability.tracing import get_tracer
from app.state import AGENT_SEQUENCE, StudioState

logger = logging.getLogger(__name__)

_PLAN_SYSTEM = (
    "You are the Supervisor of a drone-shop merchandising studio. In two sentences, "
    "outline how you'll use a Sales Analyst, an Evidence/RAG agent, a Code Interpreter, "
    "a Product Copy writer, and a Presenter to answer the request. Be concise."
)


def supervisor_node(state: StudioState) -> StudioState:
    """Decide the next agent (or 'done') and bump the step counter."""
    settings = get_settings()
    tracer = get_tracer()
    completed = list(state.get("completed", []))
    step = int(state.get("step", 0)) + 1

    with tracer.start_as_current_span("coordinator.supervisor") as span:
        span.set_attribute("studio.step", step)
        span.set_attribute("studio.completed", ",".join(completed) or "none")

        # One planning LLM call on first entry (best-effort; never fatal).
        update: StudioState = {"step": step}
        if step == 1:
            try:
                plan, usage = call_llm(
                    agent="supervisor",
                    operation="plan",
                    system_prompt=_PLAN_SYSTEM,
                    user_prompt=state.get("request", ""),
                )
                update["messages"] = [{"role": "assistant", "content": f"Plan: {plan}"}]
                update["token_usage"] = {"input": usage.get("input", 0), "output": usage.get("output", 0)}
            except Exception as exc:  # pragma: no cover - demo resilience
                logger.warning("Supervisor planning call failed: %s", exc)
                span.record_exception(exc)

        # Deterministic routing: next not-yet-completed agent, else done.
        next_agent = "done"
        for agent in AGENT_SEQUENCE:
            if agent not in completed:
                next_agent = agent
                break
        if step > settings.max_steps:
            next_agent = "done"

        span.set_attribute("studio.next_agent", next_agent)
        update["next_agent"] = next_agent
        return update


def route_from_supervisor(state: StudioState) -> str:
    """Conditional-edge selector: returns the next node name or END sentinel."""
    nxt = state.get("next_agent", "done")
    return nxt if nxt in AGENT_SEQUENCE else "done"
