"""Unit tests for the env-driven admin seed credential.

The admin account gates the admin-host AI Studio sign-in
(``POST /api/ai-studio/login``). In production its password is supplied via the
``SEED_ADMIN_PASSWORD`` secret rather than the committed default hash, so the
live credential is never baked into the image. These tests pin that contract.
"""

from __future__ import annotations

import bcrypt
import pytest

from server import database

DEFAULT_ADMIN_HASH = "$2b$12$stDMKhq3T8ZSu.c.JV/AuuhFkvdoLMWTZeY/wzArJl1fzv2thZ7ZW"
DEFAULT_SUPPORT_HASH = "$2b$12$6/edty/KrokG.3FKAuOMm.6l25OyUK8i6om6aVVgu2wGPgHGdHrd."


@pytest.mark.unit
def test_no_override_returns_committed_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "_SEED_ADMIN_PASSWORD", "")
    assert (
        database._resolve_seed_password_hash("admin", None, DEFAULT_ADMIN_HASH)
        == DEFAULT_ADMIN_HASH
    )
    assert (
        database._resolve_seed_password_hash("admin", DEFAULT_ADMIN_HASH, DEFAULT_ADMIN_HASH)
        == DEFAULT_ADMIN_HASH
    )


@pytest.mark.unit
def test_override_hashes_new_password_when_no_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "_SEED_ADMIN_PASSWORD", "S3cret-Demo-Pw")
    result = database._resolve_seed_password_hash("admin", None, DEFAULT_ADMIN_HASH)
    assert result != DEFAULT_ADMIN_HASH
    assert bcrypt.checkpw(b"S3cret-Demo-Pw", result.encode("utf-8"))


@pytest.mark.unit
def test_override_is_idempotent_when_existing_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "_SEED_ADMIN_PASSWORD", "S3cret-Demo-Pw")
    existing = bcrypt.hashpw(b"S3cret-Demo-Pw", bcrypt.gensalt()).decode("ascii")
    # Already correct → return the existing hash unchanged (no new salt/rewrite).
    assert (
        database._resolve_seed_password_hash("admin", existing, DEFAULT_ADMIN_HASH)
        == existing
    )


@pytest.mark.unit
def test_override_rehashes_when_existing_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "_SEED_ADMIN_PASSWORD", "Rotated-Pw-2")
    # Existing DB hash is the old default (does not verify the new password).
    result = database._resolve_seed_password_hash("admin", DEFAULT_ADMIN_HASH, DEFAULT_ADMIN_HASH)
    assert result != DEFAULT_ADMIN_HASH
    assert bcrypt.checkpw(b"Rotated-Pw-2", result.encode("utf-8"))


@pytest.mark.unit
def test_override_only_applies_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "_SEED_ADMIN_PASSWORD", "S3cret-Demo-Pw")
    # Non-admin seed users keep their committed default hash.
    assert (
        database._resolve_seed_password_hash("support", DEFAULT_SUPPORT_HASH, DEFAULT_SUPPORT_HASH)
        == DEFAULT_SUPPORT_HASH
    )
    assert (
        database._resolve_seed_password_hash("support", None, DEFAULT_SUPPORT_HASH)
        == DEFAULT_SUPPORT_HASH
    )
