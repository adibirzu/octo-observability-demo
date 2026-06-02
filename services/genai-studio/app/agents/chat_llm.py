"""Chat LLM helpers: multi-turn (history-aware) completion + token-streaming.

Complements ``agents/common.call_llm`` (single-shot) with a conversation-aware
path: prior turns are replayed as alternating Human/AI messages so the model has
context. Both paths open an ``llm.invoke.chat`` span carrying the same gen_ai.*
attributes consumed by OCI APM and Langfuse, plus ``gen_ai.conversation.id`` and
a first-token latency for the streaming path.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import get_settings
from app.llm import get_llm, provider_family
from app.observability.llm_tracing import llm_span


def _build_messages(system: str, history: list[dict[str, str]], user: str) -> list[Any]:
    """Assemble LangChain messages: system + replayed history + new user turn."""
    messages: list[Any] = [SystemMessage(content=system)]
    for turn in history:
        role = (turn.get("role") or "").lower()
        content = turn.get("content") or ""
        if not content:
            continue
        if role in {"assistant", "ai"}:
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user))
    return messages


def _usage_from_callback(usage_cb: Any) -> dict[str, int]:
    data = getattr(usage_cb, "usage_metadata", None) or {}
    total_in = total_out = 0
    for model_usage in data.values():
        total_in += int((model_usage or {}).get("input_tokens", 0) or 0)
        total_out += int((model_usage or {}).get("output_tokens", 0) or 0)
    return {"input": total_in, "output": total_out}


def _content_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):
        return " ".join(
            str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content
        ).strip()
    return str(content or "").strip()


def chat_complete(*, agent: str, system: str, history: list[dict[str, str]], user: str,
                  conversation_id: str = "") -> tuple[str, dict[str, int]]:
    """History-aware, non-streaming chat turn → (text, token_usage)."""
    settings = get_settings()
    model_id = settings.genai_model_id
    llm = get_llm()
    messages = _build_messages(system, history, user)

    with llm_span(operation="chat", model=model_id, system="oci_genai", agent=agent) as gen:
        gen.span.set_attribute("gen_ai.provider.name", provider_family(model_id))
        if conversation_id:
            gen.span.set_attribute("gen_ai.conversation.id", conversation_id)
        gen.span.set_attribute("gen_ai.request.turns", len(history) + 1)
        gen.set_request_params(max_tokens=settings.genai_max_tokens, temperature=settings.genai_temperature)
        gen.set_prompt(user, role="user")
        try:
            with get_usage_metadata_callback() as usage_cb:
                response = llm.invoke(messages)
            usage = _usage_from_callback(usage_cb)
        except Exception as exc:
            gen.record_error(exc)
            raise
        text = _content_text(response)
        gen.set_completion(text)
        gen.set_tokens(input=usage.get("input"), output=usage.get("output"))
        return text, usage


def chat_stream(*, agent: str, system: str, history: list[dict[str, str]], user: str,
                conversation_id: str = "", on_complete=None) -> Iterator[str]:
    """History-aware streaming chat turn.

    Yields text deltas as they arrive; the ``llm.invoke.chat`` span stays open for
    the whole stream and records first-token latency + final tokens/completion.
    ``on_complete(full_text, usage)`` is called once at the end (e.g. to persist
    the assistant turn to the conversation store).
    """
    settings = get_settings()
    model_id = settings.genai_model_id
    llm = get_llm()
    messages = _build_messages(system, history, user)

    with llm_span(operation="chat", model=model_id, system="oci_genai", agent=agent) as gen:
        gen.span.set_attribute("gen_ai.provider.name", provider_family(model_id))
        gen.span.set_attribute("gen_ai.request.streaming", True)
        if conversation_id:
            gen.span.set_attribute("gen_ai.conversation.id", conversation_id)
        gen.span.set_attribute("gen_ai.request.turns", len(history) + 1)
        gen.set_request_params(max_tokens=settings.genai_max_tokens, temperature=settings.genai_temperature)
        gen.set_prompt(user, role="user")

        parts: list[str] = []
        started = time.monotonic()
        first_token_at: float | None = None
        try:
            with get_usage_metadata_callback() as usage_cb:
                for chunk in llm.stream(messages):
                    delta = _content_text(chunk)
                    if not delta:
                        continue
                    if first_token_at is None:
                        first_token_at = time.monotonic()
                        gen.span.set_attribute(
                            "gen_ai.response.time_to_first_token_ms",
                            round((first_token_at - started) * 1000, 1),
                        )
                    parts.append(delta)
                    yield delta
            usage = _usage_from_callback(usage_cb)
        except Exception as exc:
            gen.record_error(exc)
            raise
        full = "".join(parts).strip()
        gen.set_completion(full)
        gen.set_tokens(input=usage.get("input"), output=usage.get("output"))
        if on_complete:
            on_complete(full, usage)
