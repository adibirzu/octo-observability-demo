"""Offline OIDC signature and claim verification with generated RSA fixtures."""
import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from server.modules import auth


@pytest.fixture(scope="module")
def signing_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


@pytest.fixture
def oidc(monkeypatch, signing_keys):
    keys = []
    for kid, key in zip(["other", "current"], signing_keys):
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk["kid"] = kid
        jwk["alg"] = "RS256"
        keys.append(jwk)
    monkeypatch.setattr(auth, "cfg", SimpleNamespace(idcs_domain_url="https://identity.example.invalid"))
    discovery = AsyncMock(return_value={"issuer": "https://identity.example.invalid", "jwks_uri": "https://identity.example.invalid/keys"})
    jwks = AsyncMock(return_value={"keys": keys})
    monkeypatch.setattr(auth, "_fetch_oidc_discovery", discovery)
    monkeypatch.setattr(auth, "_fetch_jwks", jwks)
    return signing_keys[1], keys, jwks


def claims():
    return {"iss": "https://identity.example.invalid", "aud": "crm-client",
            "exp": int(time.time()) + 300, "sub": "subject", "nonce": "expected-nonce"}


def verify(token, nonce="expected-nonce"):
    return asyncio.run(auth._verify_id_token(token, nonce, "crm-client"))


@pytest.mark.parametrize("algorithm", ["RS256", "RS384", "RS512"])
def test_rsa_signature_and_kid_selection(oidc, algorithm):
    key, _, _ = oidc
    expected = claims()
    token = jwt.encode(expected, key, algorithm=algorithm, headers={"kid": "current"})
    assert verify(token) == expected


def test_verification_works_without_removed_jose_package(oidc, monkeypatch):
    key, _, _ = oidc
    monkeypatch.setitem(sys.modules, "jose", None)
    token = jwt.encode(claims(), key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token)["sub"] == "subject"


@pytest.mark.parametrize("updates", [
    {"exp": 1}, {"aud": "another-client"}, {"iss": "https://other.example.invalid"},
    {"nonce": "wrong"}, {"nbf": 9999999999},
])
def test_invalid_claims_are_rejected(oidc, updates):
    key, _, _ = oidc
    body = claims()
    body.update(updates)
    token = jwt.encode(body, key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token) is None


def test_wrong_signature_is_rejected(oidc, signing_keys):
    token = jwt.encode(claims(), signing_keys[0], algorithm="RS256", headers={"kid": "current"})
    assert verify(token) is None


def test_unknown_kid_is_rejected_after_refresh(oidc):
    key, _, fetch = oidc
    token = jwt.encode(claims(), key, algorithm="RS256", headers={"kid": "missing"})
    assert verify(token) is None
    assert fetch.await_count == 2


def test_rotated_key_is_selected_after_refresh(oidc):
    key, keys, fetch = oidc
    fetch.side_effect = [{"keys": keys[:1]}, {"keys": keys}]
    token = jwt.encode(claims(), key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token)["sub"] == "subject"
    assert fetch.await_count == 2


def test_none_algorithm_is_rejected(oidc):
    token = jwt.encode(claims(), "", algorithm="none", headers={"kid": "current"})
    assert verify(token) is None


def test_hmac_with_public_der_key_is_rejected(oidc):
    key, _, _ = oidc
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")
    content = encode({"alg": "HS256", "kid": "current"}) + b"." + encode(claims())
    public_der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    signature = base64.urlsafe_b64encode(hmac.new(public_der, content, hashlib.sha256).digest()).rstrip(b"=")
    assert verify((content + b"." + signature).decode()) is None


def test_malformed_token_is_rejected(oidc):
    assert verify("malformed") is None


def test_future_issued_at_preserves_existing_jose_policy(oidc):
    key, _, _ = oidc
    body = claims()
    body["iat"] = int(time.time()) + 3600
    token = jwt.encode(body, key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token) == body


@pytest.mark.parametrize("issued_at", ["invalid", None, {}, [], float("inf"), float("-inf"), float("nan")],
                         ids=["text", "null", "object", "array", "positive-infinity", "negative-infinity", "nan"])
def test_non_numeric_issued_at_is_rejected(oidc, issued_at):
    key, _, _ = oidc
    body = claims()
    body["iat"] = issued_at
    token = jwt.encode(body, key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token) is None


@pytest.mark.parametrize("audience", [None, "", []], ids=["missing", "empty-string", "empty-list"])
def test_configured_audience_rejects_missing_or_empty_claim(oidc, audience):
    key, _, _ = oidc
    body = claims()
    if audience is None:
        body.pop("aud")
    else:
        body["aud"] = audience
    token = jwt.encode(body, key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token) is None


def test_audience_list_containing_configured_client_is_accepted(oidc):
    key, _, _ = oidc
    body = claims()
    body["aud"] = ["crm-client", "another-client"]
    token = jwt.encode(body, key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token) == body


def test_missing_expiry_is_rejected(oidc):
    key, _, _ = oidc
    body = claims()
    body.pop("exp")
    token = jwt.encode(body, key, algorithm="RS256", headers={"kid": "current"})
    assert verify(token) is None
