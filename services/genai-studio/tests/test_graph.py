"""The compiled graph runs all five agents in order and terminates with a brief."""

from __future__ import annotations

import pytest

from app.graph import build_graph, recursion_limit
from app.state import AGENT_SEQUENCE, empty_state


@pytest.mark.unit
def test_graph_runs_all_agents_and_terminates():
    graph = build_graph()
    state = empty_state(request="merchandising brief for thermal mapping drones", run_id="t1")
    final = graph.invoke(state, config={"recursion_limit": recursion_limit()})

    # Every agent ran exactly once, in sequence.
    assert final["completed"] == list(AGENT_SEQUENCE)
    # Presenter produced a non-empty markdown brief.
    assert final["brief"].startswith("# Merchandising Brief")
    assert "Sales snapshot" in final["brief"]
    # Code interpreter produced a chart from synthetic data.
    assert final["chart"]["computed"] is True
    assert final["chart"]["chart_png_base64"]


@pytest.mark.unit
def test_supervisor_routes_to_done_after_presenter():
    from app.agents.supervisor import route_from_supervisor

    assert route_from_supervisor({"next_agent": "done"}) == "done"
    assert route_from_supervisor({"next_agent": "sales_analyst"}) == "sales_analyst"
