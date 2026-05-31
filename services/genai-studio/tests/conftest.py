"""Test fixtures: stub the LLM so the graph runs without OCI credentials."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `import app...` work when running pytest from the service dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    """Replace the agent LLM call with a deterministic stub (no network)."""

    def fake_call_llm(*, agent, system_prompt, user_prompt, operation="chat"):
        return f"[{agent}] stub response", {"input": 10, "output": 20}

    # Patch the symbol where each agent imported it.
    for module in (
        "app.agents.supervisor",
        "app.agents.evidence",
        "app.agents.product_copy",
        "app.agents.data_qa",
        "app.agents.rag",
    ):
        monkeypatch.setattr(module + ".call_llm", fake_call_llm, raising=True)
    yield
