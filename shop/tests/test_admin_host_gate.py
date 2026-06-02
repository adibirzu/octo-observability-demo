"""AI Studio + GenAI Observability are admin-host-only.

These surfaces must not be served on the public storefront host
(drones.<DNS_DOMAIN>); they answer only on the admin host (admin.<DNS_DOMAIN>).
The gate returns 404 on the wrong host so the surface isn't even discoverable
there, and the nav link / admin-console card are hidden off-host.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("AI_STUDIO_ENABLED", "true")
    monkeypatch.setenv("AI_STUDIO_BASE_URL", "http://studio.local:8090")
    monkeypatch.setenv("DNS_DOMAIN", "example.test")  # admin host = admin.example.test
    import server.config as config
    importlib.reload(config)
    # The proxy module binds `cfg` + auth helpers at import time; reload it so its
    # references track the DNS-configured config (avoids cross-test reload bleed).
    import server.modules.ai_studio as ai_studio
    importlib.reload(ai_studio)
    import server.main as main
    importlib.reload(main)
    return main


# ── config helper ────────────────────────────────────────────────────────
@pytest.mark.unit
def test_admin_hostname_derived_from_dns_domain(admin_app):
    assert admin_app.cfg.admin_public_hostname == "admin.example.test"


@pytest.mark.unit
def test_is_admin_host_matrix(admin_app):
    c = admin_app.cfg
    assert c.is_admin_host("admin.example.test") is True
    assert c.is_admin_host("admin.example.test:443") is True
    assert c.is_admin_host("localhost") is True  # dev convenience
    assert c.is_admin_host("drones.example.test") is False
    assert c.is_admin_host("example.test") is False


@pytest.mark.unit
def test_gate_disabled_without_dns_domain(monkeypatch):
    monkeypatch.delenv("DNS_DOMAIN", raising=False)
    monkeypatch.delenv("ADMIN_PUBLIC_HOST", raising=False)
    monkeypatch.delenv("SHOP_PUBLIC_URL", raising=False)
    import server.config as config
    importlib.reload(config)
    # No admin host configured -> gate is OFF (single-host/local dev).
    assert config.cfg.admin_public_hostname == ""
    assert config.cfg.is_admin_host("anything.example") is True
    importlib.reload(config)  # restore for other tests


# ── route gate ────────────────────────────────────────────────────────────
def _client(main):
    from fastapi.testclient import TestClient
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.mark.unit
def test_ai_studio_404_on_public_host(admin_app):
    r = _client(admin_app).get(
        "/ai-studio", headers={"host": "drones.example.test"}, follow_redirects=False
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_ai_studio_not_404_on_admin_host(admin_app):
    # On the admin host the host gate passes; unauthenticated -> login redirect
    # (302) or rendered page (200) — never 404.
    r = _client(admin_app).get(
        "/ai-studio", headers={"host": "admin.example.test"}, follow_redirects=False
    )
    assert r.status_code != 404


@pytest.mark.unit
def test_genai_observability_404_on_public_host(admin_app):
    r = _client(admin_app).get(
        "/admin/genai-observability", headers={"host": "drones.example.test"},
        follow_redirects=False,
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_ai_studio_proxy_404_on_public_host(admin_app):
    # Browser POST to the GenAI proxy on the public host is not discoverable.
    r = _client(admin_app).post(
        "/api/ai-studio/ask",
        headers={"host": "drones.example.test", "content-type": "application/json"},
        json={"question": "hi"},
        follow_redirects=False,
    )
    assert r.status_code == 404


# ── AI Studio sign-in (admin-host-scoped, cookie-issuing) ──────────────────
@pytest.mark.unit
def test_ai_studio_login_page_on_admin_host(admin_app):
    r = _client(admin_app).get(
        "/ai-studio/login", headers={"host": "admin.example.test"}, follow_redirects=False
    )
    assert r.status_code == 200
    assert "AI Studio Sign-in" in r.text


@pytest.mark.unit
def test_ai_studio_login_page_404_on_public_host(admin_app):
    r = _client(admin_app).get(
        "/ai-studio/login", headers={"host": "drones.example.test"}, follow_redirects=False
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_unauth_ai_studio_redirects_to_studio_login_not_crm_login(admin_app):
    # On the admin host an unauthenticated admin must be sent to the shop-served
    # /ai-studio/login (LB-routed to shop), NOT /login (which serves the CRM there).
    r = _client(admin_app).get(
        "/ai-studio", headers={"host": "admin.example.test"}, follow_redirects=False
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/ai-studio/login"


@pytest.mark.unit
def test_ai_studio_login_post_404_on_public_host(admin_app):
    # The cookie-issuing login endpoint is not discoverable on the storefront host.
    r = _client(admin_app).post(
        "/api/ai-studio/login",
        headers={"host": "drones.example.test", "content-type": "application/json"},
        json={"username": "x", "password": "y"},
        follow_redirects=False,
    )
    assert r.status_code == 404
