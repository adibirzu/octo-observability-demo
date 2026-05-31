"""Shared helpers for agent nodes: a traced LLM call carrying gen_ai.* telemetry."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.llm import get_llm, provider_family
from app.observability.llm_tracing import llm_span

logger = logging.getLogger(__name__)


def call_llm(*, agent: str, system_prompt: str, user_prompt: str, operation: str = "chat") -> tuple[str, dict[str, int]]:
    """Invoke ChatOCIGenAI inside an llm.invoke span; return (text, token_usage).

    Wraps the call so every model invocation emits gen_ai.* attributes consumed
    by both OCI APM and Langfuse. Token usage is extracted best-effort from the
    LangChain response metadata.
    """
    settings = get_settings()
    model_id = settings.genai_model_id
    llm = get_llm()

    with llm_span(operation=operation, model=model_id, system="oci_genai", agent=agent) as gen:
        gen.span.set_attribute("gen_ai.provider.name", provider_family(model_id))
        gen.set_request_params(
            max_tokens=settings.genai_max_tokens,
            temperature=settings.genai_temperature,
        )
        gen.set_prompt(user_prompt, role="user")
        try:
            # Aggregate token usage via the LangChain callback — reliable across
            # runtimes where the provider does not populate AIMessage.usage_metadata
            # (observed under uvicorn with langchain-oci). Falls back to response
            # introspection if the callback yields nothing.
            with get_usage_metadata_callback() as usage_cb:
                response = llm.invoke(
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
            usage = _usage_from_callback(usage_cb) or _token_usage(response)
        except Exception as exc:
            gen.record_error(exc)
            raise

        text = _content_text(response)
        gen.set_completion(text)
        gen.set_tokens(input=usage.get("input"), output=usage.get("output"))
        gen.set_finish_reason(_finish_reason(response))
        return text, usage


def _usage_from_callback(usage_cb: Any) -> dict[str, int]:
    """Sum per-model usage collected by the LangChain usage-metadata callback."""
    data = getattr(usage_cb, "usage_metadata", None) or {}
    total_in = total_out = 0
    for model_usage in data.values():
        total_in += int((model_usage or {}).get("input_tokens", 0) or 0)
        total_out += int((model_usage or {}).get("output_tokens", 0) or 0)
    if total_in or total_out:
        return {"input": total_in, "output": total_out}
    return {}


def _content_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):  # some providers return content blocks
        return " ".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content
        ).strip()
    return str(content or "").strip()


def _token_usage(response: Any) -> dict[str, int]:
    meta = getattr(response, "usage_metadata", None) or {}
    if meta:
        return {
            "input": int(meta.get("input_tokens", 0) or 0),
            "output": int(meta.get("output_tokens", 0) or 0),
        }
    resp_meta = getattr(response, "response_metadata", {}) or {}
    usage = resp_meta.get("usage") or resp_meta.get("token_usage") or {}
    return {
        "input": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        "output": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
    }


def _finish_reason(response: Any) -> str:
    resp_meta = getattr(response, "response_metadata", {}) or {}
    return str(resp_meta.get("finish_reason") or resp_meta.get("stop_reason") or "stop")
