"""Phase 4: AI Studio LLM-as-a-judge evaluator template definitions are well-formed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the scripts/ dir importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ensure_evaluator_templates as ev  # noqa: E402


@pytest.mark.unit
def test_four_evaluators_defined():
    defs = ev.evaluator_definitions()
    names = {d["name"] for d in defs}
    assert names == {
        "ai-studio-brief-groundedness",
        "ai-studio-sales-accuracy",
        "ai-studio-copy-quality",
        "ai-studio-safety",
    }


@pytest.mark.unit
def test_each_evaluator_is_complete():
    for d in ev.evaluator_definitions():
        assert d["prompt"].strip()
        assert d["model"]
        assert d["provider"] == "oci-genai"
        assert "score" in d["outputSchema"]
        assert "{{output}}" in d["prompt"]  # every judge sees the agent output


@pytest.mark.unit
def test_template_payload_infers_vars_from_prompt():
    groundedness = next(
        d for d in ev.evaluator_definitions() if d["name"] == "ai-studio-brief-groundedness"
    )
    payload = ev._template_payload(groundedness)
    # The groundedness prompt references {{sales}}, {{evidence}}, {{output}}.
    assert set(payload["vars"]) == {"sales", "evidence", "output"}
    assert payload["model"] == groundedness["model"]
    assert payload["outputSchema"]["score"].startswith("float")


@pytest.mark.unit
def test_structured_output_probe_schema_is_valid_json_schema():
    import check_oci_genai_structured_output as chk

    schema = chk._PROBE_SCHEMA["json_schema"]["schema"]
    assert schema["required"] == ["score", "reasoning"]
    assert schema["properties"]["score"]["type"] == "number"


@pytest.mark.unit
def test_base_url_builds_openai_compatible_endpoint():
    import check_oci_genai_structured_output as chk

    url = chk._base_url("eu-frankfurt-1", None)
    assert url == "https://inference.generativeai.eu-frankfurt-1.oci.oraclecloud.com/openai/v1"
    assert chk._base_url("x", "https://custom/openai/v1/") == "https://custom/openai/v1"
