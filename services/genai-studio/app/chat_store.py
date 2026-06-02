"""In-process, bounded per-session conversation memory for AI Studio chat.

The classic assistant stores history but never feeds it back to the model; this
store is what makes AI Studio chat genuinely *multi-turn* — the last N turns are
replayed into each LLM call. Kept deliberately simple and process-local (no DB
dependency): a bounded ring per session with a soft TTL, so memory cannot grow
unbounded and stale sessions are evicted. Conversation grouping in OCI APM /
Langfuse is by ``session.id`` (the same key), so the trace view and the in-memory
history line up one-to-one.

NOTE: process-local means history is not shared across replicas. For the demo's
single-writer studio that is fine; the documented upgrade is a Redis/ATP-backed
store keyed on the same session id.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

# Bounds (env-tunable at the call sites, not here, to keep this module pure).
MAX_TURNS_PER_SESSION = 12  # user+assistant messages retained (6 exchanges)
MAX_SESSIONS = 500  # LRU cap across all sessions
MAX_CONTENT_CHARS = 4000  # clamp any single stored message


@dataclass
class _Session:
    messages: list[dict[str, str]] = field(default_factory=list)


class ChatStore:
    """Thread-safe, LRU-bounded conversation store keyed by session id."""

    def __init__(self, max_sessions: int = MAX_SESSIONS, max_turns: int = MAX_TURNS_PER_SESSION) -> None:
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._lock = threading.Lock()
        self._sessions: "OrderedDict[str, _Session]" = OrderedDict()

    def history(self, session_id: str) -> list[dict[str, str]]:
        """Return a copy of the stored turns for a session (oldest first)."""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return []
            self._sessions.move_to_end(session_id)
            return list(sess.messages)

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append one message; trims to the last N turns and evicts LRU sessions."""
        clean = (content or "").strip()[:MAX_CONTENT_CHARS]
        if not clean:
            return
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                sess = _Session()
                self._sessions[session_id] = sess
            sess.messages.append({"role": role, "content": clean})
            if len(sess.messages) > self._max_turns:
                sess.messages = sess.messages[-self._max_turns :]
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def turn_count(self, session_id: str) -> int:
        with self._lock:
            sess = self._sessions.get(session_id)
            return len(sess.messages) if sess else 0


# Process-wide singleton used by the chat agent + endpoint.
_STORE = ChatStore()


def get_chat_store() -> ChatStore:
    return _STORE
