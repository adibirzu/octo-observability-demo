"""Cross-app SSO bridge: the CRM mints the shop's `octo_session` cookie.

On login the CRM issues a token the Drone Shop accepts, so one admin-host login
also authenticates AI Studio. These tests pin the token format to the shop's
verifier algorithm (shop/server/auth_security.py: base64url(json).HMAC, signed
with sha256(AUTH_TOKEN_SECRET)) so the two stay byte-compatible.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest

from server.modules import auth


def _shop_verify(token: str, secret: str) -> dict | None:
    """Re-implementation of shop verify_token — the contract the CRM must meet."""
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    secret_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    expected = (
        base64.urlsafe_b64encode(hmac.new(secret_bytes, body.encode("utf-8"), hashlib.sha256).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    if not hmac.compare_digest(signature, expected):
        return None
    padding = "=" * (-len(body) % 4)
    payload = json.loads(base64.urlsafe_b64decode(f"{body}{padding}").decode("utf-8"))
    if int(payload.get("exp", 0) or 0) <= int(time.time()):
        return None
    return payload


@pytest.fixture
def _secret(monkeypatch: pytest.MonkeyPatch) -> str:
    material = "unit-test-signing-material"
    monkeypatch.setattr(auth, "cfg", SimpleNamespace(auth_token_secret=material))
    return material


def test_minted_token_is_accepted_by_shop_verifier(_secret: str) -> None:
    token = auth._mint_shop_session_token(6, "crm-admin", "admin")
    assert token and token.count(".") == 1
    payload = _shop_verify(token, _secret)
    assert payload is not None, "shop verifier must accept the CRM-minted token"
    assert payload["sub"] == 6
    assert payload["username"] == "crm-admin"
    assert payload["role"] == "admin"
    assert payload["auth_method"] == "password"
    assert payload["exp"] > int(time.time())


def test_token_carries_real_role_not_hardcoded_admin(_secret: str) -> None:
    # A non-admin login must NOT be elevated; the shop's AI Studio gate then rejects it.
    payload = _shop_verify(auth._mint_shop_session_token(9, "support", "support"), _secret)
    assert payload is not None and payload["role"] == "support"


def test_wrong_secret_is_rejected(_secret: str) -> None:
    token = auth._mint_shop_session_token(6, "crm-admin", "admin")
    assert _shop_verify(token, "a-different-secret") is None


def test_bridge_disabled_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "cfg", SimpleNamespace(auth_token_secret=""))
    assert auth._mint_shop_session_token(6, "crm-admin", "admin") is None
