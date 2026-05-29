"""Input governance for the AI Studio boundary.

Ported from the Drone Shop's assistant_service.assistant_scope_decision so the
agentic surface enforces the same drone-domain scope + prompt-injection blocks
as the classic single-turn assistant.
"""

from __future__ import annotations

_ALLOWED_TERMS = {
    "drone", "drones", "uav", "uas", "quadcopter", "octocopter", "vtol", "fpv",
    "payload", "payloads", "sensor", "sensors", "camera", "thermal", "lidar",
    "rtk", "ppk", "gnss", "gimbal", "mesh", "range", "endurance", "flight",
    "battery", "mapping", "survey", "inspection", "cinema", "agriculture",
    "public safety", "search", "rescue", "ndaa", "stock", "price", "pricing",
    "cost", "sku", "catalog", "compare", "recommend", "mission", "spec", "specs",
    "shipping", "checkout", "warranty", "merchandising", "marketing", "brief",
    "sales", "trend", "revenue", "category", "campaign", "bundle", "promotion",
}
_BLOCKED_TERMS = {
    "ignore previous", "ignore the previous", "system prompt", "developer message",
    "secret", "password", "api key", "token", "jailbreak", "malware", "exploit",
    "drop table", "delete from", "credit card number", "ssn",
}


def scope_decision(message: str) -> tuple[bool, str]:
    """Return (allowed, reason) for a studio request."""
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return False, "empty_message"
    if any(term in normalized for term in _BLOCKED_TERMS):
        return False, "blocked_term"
    if any(term in normalized for term in _ALLOWED_TERMS):
        return True, "drone_domain_keyword"
    return False, "out_of_scope"


def bounded(value: object, *, limit: int) -> str:
    """Collapse whitespace and clamp to a max length."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())[:limit]
