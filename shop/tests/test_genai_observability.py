"""Guards for the admin GenAI Observability page + its deep-link config.

The route renders cfg deep-link fields directly; a missing attribute would 500 on
the first admin visit (not caught by the proxy tests). These tests pin both the
route registration and the cfg attributes so that regression can't recur.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def app_with_studio(monkeypatch):
    monkeypatch.setenv("AI_STUDIO_ENABLED", "true")
    monkeypatch.setenv("AI_STUDIO_BASE_URL", "http://studio.local:8090")
    import server.config as config
    importlib.reload(config)
    import server.main as main
    importlib.reload(main)
    return main


@pytest.mark.unit
def test_obs_route_registered(app_with_studio):
    paths = {getattr(r, "path", None) for r in app_with_studio.app.routes}
    assert "/admin/genai-observability" in paths


@pytest.mark.unit
def test_obs_metrics_proxy_route_registered(app_with_studio):
    paths = {getattr(r, "path", None) for r in app_with_studio.app.routes}
    assert "/api/ai-studio/metrics" in paths


@pytest.mark.unit
def test_cfg_has_deeplink_fields(app_with_studio):
    """The obs page reads these directly — they MUST exist (the 500 regression)."""
    cfg = app_with_studio.cfg
    for attr in ("apm_console_url", "langfuse_dashboard_url", "grafana_url", "genai_command_center_url"):
        assert hasattr(cfg, attr), f"cfg missing {attr}"


@pytest.mark.unit
def test_obs_page_redirects_anonymous(app_with_studio):
    """No admin session and no key → redirect to /login (302), never a 500."""
    from fastapi.testclient import TestClient

    client = TestClient(app_with_studio.app, raise_server_exceptions=True, follow_redirects=False)
    resp = client.get("/admin/genai-observability")
    assert resp.status_code in (302, 401, 403)
