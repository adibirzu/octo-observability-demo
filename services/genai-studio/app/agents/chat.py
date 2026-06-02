"""Conversational chat agent for AI Studio — multi-turn, telemetry-grounded.

A genuinely multi-turn surface (distinct from the single-shot brief/ask/rag):
prior turns are replayed into each LLM call from the in-process conversation
store, so the model has context. Every turn opens
``agent.invoke.chat_assistant`` → ``llm.invoke.chat`` carrying gen_ai.* + the
conversation id, so a whole conversation is one correlatable session in OCI APM
and Langfuse (grouped by ``session.id``).
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from app.agents.chat_llm import chat_complete, chat_stream
from app.chat_store import get_chat_store
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are the OCTO Drone Shop assistant. Hold a helpful, concise conversation "
    "about drones, payloads, specs, pricing, orders, and shop policies. Use the "
    "prior turns for context. If you don't know something, say so — never invent "
    "specifications, prices, or policies. Stay within the drone-shop domain."
)


def answer_chat(question: str, session_id: str) -> dict[str, Any]:
    """One non-streaming chat turn; persists both sides to the conversation store."""
    store = get_chat_store()
    history = store.history(session_id)
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.invoke.chat_assistant") as span:
        span.set_attribute("gen_ai.agent.name", "chat_assistant")
        span.set_attribute("gen_ai.conversation.id", session_id)
        span.set_attribute("studio.chat.history_turns", len(history))
        span.set_attribute("studio.question_length", len(question))
        answer, usage = "", {"input": 0, "output": 0}
        try:
            answer, usage = chat_complete(
                agent="chat_assistant", system=_SYSTEM, history=history,
                user=question, conversation_id=session_id,
            )
        except Exception as exc:  # pragma: no cover - resilience
            logger.warning("Chat LLM failed: %s", exc)
            span.record_exception(exc)
            answer = "The assistant is temporarily unavailable. Please retry."
        span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("input", 0)))
        span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("output", 0)))

    store.append(session_id, "user", question)
    if answer:
        store.append(session_id, "assistant", answer)
    return {
        "answer": answer,
        "token_usage": usage,
        "history_turns": len(history) + 2,
        "session_id": session_id,
    }


def stream_chat(question: str, session_id: str) -> Iterator[str]:
    """One streaming chat turn; yields text deltas, persists both sides at end."""
    store = get_chat_store()
    history = store.history(session_id)
    tracer = get_tracer()
    # Persist the user turn up-front so it's retained even if the client aborts.
    store.append(session_id, "user", question)

    def _persist(full_text: str, _usage: dict) -> None:
        if full_text:
            store.append(session_id, "assistant", full_text)

    with tracer.start_as_current_span("agent.invoke.chat_assistant") as span:
        span.set_attribute("gen_ai.agent.name", "chat_assistant")
        span.set_attribute("gen_ai.conversation.id", session_id)
        span.set_attribute("studio.chat.history_turns", len(history))
        span.set_attribute("studio.chat.streaming", True)
        yield from chat_stream(
            agent="chat_assistant", system=_SYSTEM, history=history,
            user=question, conversation_id=session_id, on_complete=_persist,
        )
