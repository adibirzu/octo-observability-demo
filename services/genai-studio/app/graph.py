"""LangGraph StateGraph wiring the supervisor and the five agents.

    START → supervisor ─►(conditional)─► sales_analyst → supervisor
                                         evidence       → supervisor
                                         code_interpreter→ supervisor
                                         product_copy    → supervisor
                                         presenter       → supervisor → END

The supervisor re-enters between every agent and routes to the next not-yet-run
agent, terminating once the presenter has produced the brief or STUDIO_MAX_STEPS
is hit. This is the deterministic supervisor pattern from oci-coordinator-oke.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.code_interpreter import code_interpreter_node
from app.agents.evidence import evidence_node
from app.agents.presenter import presenter_node
from app.agents.product_copy import product_copy_node
from app.agents.sales_analyst import sales_analyst_node
from app.agents.supervisor import route_from_supervisor, supervisor_node
from app.config import get_settings
from app.state import AGENT_SEQUENCE, StudioState

_NODES = {
    "sales_analyst": sales_analyst_node,
    "evidence": evidence_node,
    "code_interpreter": code_interpreter_node,
    "product_copy": product_copy_node,
    "presenter": presenter_node,
}


def build_graph():
    """Construct and compile the studio StateGraph."""
    graph = StateGraph(StudioState)
    graph.add_node("supervisor", supervisor_node)
    for name, fn in _NODES.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "supervisor")
    # Supervisor decides which agent runs next (or END).
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {**{a: a for a in AGENT_SEQUENCE}, "done": END},
    )
    # Every agent reports back to the supervisor.
    for name in _NODES:
        graph.add_edge(name, "supervisor")

    return graph.compile()


@lru_cache
def get_compiled_graph():
    return build_graph()


def recursion_limit() -> int:
    # Each agent costs 2 hops (agent + supervisor); pad for the planning entry.
    return max(get_settings().max_steps, len(AGENT_SEQUENCE) * 2 + 4)
