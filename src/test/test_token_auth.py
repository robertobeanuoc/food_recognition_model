import time

import pytest
from authlib.jose import JsonWebKey
from authlib.jose import jwt as jose_jwt

import main as main_module
from food_recognition import auth as auth_module
from food_recognition.db import get_pending_chat_link_request
from conftest import TEST_OIDC_CLIENT_ID, TEST_OIDC_ISSUER

_OWNER_A = "test-owner-a"
_KID = "test-kid"


@pytest.fixture
def rsa_keypair():
    """A throwaway RSA keypair standing in for Authentik's real signing key.
    Returns (private_jwk, jwks) — the private half signs test tokens, the
    public half (as a JWKS) is what _stub_jwks below hands back instead of
    ever calling the real Authentik server.
    """
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    private_jwk = key.as_dict(is_private=True)
    private_jwk["kid"] = _KID
    public_jwk = key.as_dict(is_private=False)
    public_jwk["kid"] = _KID
    return private_jwk, {"keys": [public_jwk]}


@pytest.fixture(autouse=True)
def _stub_jwks(monkeypatch, rsa_keypair):
    _, jwks = rsa_keypair
    monkeypatch.setattr(auth_module, "_get_jwks", lambda issuer, force_refresh=False: jwks)


def _make_token(private_jwk: dict, **claim_overrides) -> str:
    now = int(time.time())
    payload = {
        "sub": _OWNER_A,
        "email": "owner-a@example.com",
        "name": "Owner A",
        "iss": TEST_OIDC_ISSUER,
        "azp": TEST_OIDC_CLIENT_ID,
        "exp": now + 300,
        "iat": now,
    }
    payload.update(claim_overrides)
    header = {"alg": "RS256", "kid": _KID}
    return jose_jwt.encode(header, payload, private_jwk).decode("utf-8")


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_valid_bearer_token_authenticates_the_request(rsa_keypair):
    private_jwk, _ = rsa_keypair
    client = main_module.app.test_client()

    response = client.post("/settings/chat/link-code", headers=_auth_headers(_make_token(private_jwk)))

    assert response.status_code == 200
    assert get_pending_chat_link_request(_OWNER_A) is not None


def test_expired_bearer_token_is_rejected(rsa_keypair):
    private_jwk, _ = rsa_keypair
    token = _make_token(private_jwk, exp=int(time.time()) - 10)
    client = main_module.app.test_client()

    response = client.post("/settings/chat/link-code", headers=_auth_headers(token))

    assert response.status_code == 401


def test_bearer_token_with_wrong_issuer_is_rejected(rsa_keypair):
    private_jwk, _ = rsa_keypair
    token = _make_token(private_jwk, iss="http://not-authentik.test/")
    client = main_module.app.test_client()

    response = client.post("/settings/chat/link-code", headers=_auth_headers(token))

    assert response.status_code == 401


def test_bearer_token_from_an_untrusted_client_is_rejected(rsa_keypair):
    """Correctly signed by the real (test) issuer, but issued to some other
    Authentik-registered client — must not be accepted just because the
    signature/issuer check alone would pass (see auth.py's azp check)."""
    private_jwk, _ = rsa_keypair
    token = _make_token(private_jwk, azp="some-other-app-client-id")
    client = main_module.app.test_client()

    response = client.post("/settings/chat/link-code", headers=_auth_headers(token))

    assert response.status_code == 401


def test_bearer_token_signed_with_an_untrusted_key_is_rejected():
    """Same kid, different key material — stands in for a tampered/forged
    signature: the stubbed JWKS only recognizes the *other* fixture's key."""
    other_key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    other_private_jwk = other_key.as_dict(is_private=True)
    other_private_jwk["kid"] = _KID
    token = _make_token(other_private_jwk)
    client = main_module.app.test_client()

    response = client.post("/settings/chat/link-code", headers=_auth_headers(token))

    assert response.status_code == 401


def test_no_bearer_token_and_no_session_is_rejected():
    client = main_module.app.test_client()

    response = client.post("/settings/chat/link-code")

    assert response.status_code == 401
