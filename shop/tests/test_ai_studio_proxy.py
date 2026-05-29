"""AI Studio proxy: disabled-by-default (503) and admin auth required."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.config import cfg
from server.modules.ai_studio import router as ai_studio_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(ai_studio_router)
    return TestClient(app, raise_server_exceptions=False)


def test_proxy_disabled_by_default() -> None:
    # The committed default keeps AI Studio off so the shop is unaffected.
    assert cfg.ai_studio_configured is False


def test_brief_requires_auth_or_returns_503() -> None:
    client = _client()
    resp = client.post("/api/ai-studio/brief", json={"request": "merchandising brief"})
    # Unauthenticated callers are rejected (401/403); if auth is bypassed in a
    # test context the unconfigured service must still refuse with 503.
    assert resp.status_code in {401, 403, 503}
