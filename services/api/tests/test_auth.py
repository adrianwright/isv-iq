from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import (
    AccessTokenValidator,
    ApiAuthError,
    get_access_token_validator,
    require_api_user,
)
from app.config import Settings, get_settings
from app.main import app

TENANT_ID = "11111111-1111-1111-1111-111111111111"
AUDIENCE = "22222222-2222-2222-2222-222222222222"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class _SigningKey:
    key: object


class _StaticJwksClient:
    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:  # noqa: ARG002
        return _SigningKey(PRIVATE_KEY.public_key())


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        AZURE_TENANT_ID=TENANT_ID,
        API_AUDIENCE=AUDIENCE,
        API_REQUIRED_SCOPE="access_as_user",
    )


def _token(**overrides: object) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        "aud": AUDIENCE,
        "tid": TENANT_ID,
        "sub": "user-123",
        "scp": "access_as_user other_scope",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key"})


def _validator() -> AccessTokenValidator:
    return AccessTokenValidator(_settings(), jwks_client=_StaticJwksClient())  # type: ignore[arg-type]


def test_validates_tenant_audience_and_scope() -> None:
    principal = _validator().validate(_token())
    assert principal.tenant_id == TENANT_ID
    assert principal.subject == "user-123"
    assert "access_as_user" in principal.scopes


def test_accepts_app_id_uri_audience_alias() -> None:
    principal = _validator().validate(_token(aud=f"api://{AUDIENCE}"))
    assert principal.subject == "user-123"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"aud": "api://wrong"}, "audience"),
        ({"tid": "33333333-3333-3333-3333-333333333333"}, "tenant"),
        ({"scp": "other_scope"}, "required scope"),
    ],
)
def test_rejects_invalid_required_claims(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ApiAuthError, match=message):
        _validator().validate(_token(**overrides))


def test_anonymous_mock_routes_succeed_but_public_routes_remain_public() -> None:
    saved = app.dependency_overrides.pop(require_api_user)
    try:
        client = TestClient(app)
        assert (
            client.post(
                "/api/isv/ask",
                json={
                    "question": "Assess the renewal.",
                    "accountId": "ACC-1001",
                    "renewalId": "REN-1001",
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/isv/ask/stream",
                json={
                    "question": "Assess the renewal.",
                    "accountId": "ACC-1001",
                    "renewalId": "REN-1001",
                },
            ).status_code
            == 200
        )
        assert client.get("/api/isv/portfolio").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/fabric/status").status_code == 200
        assert (
            client.get(
                "/api/evidence/doc",
                params={"path": "isv_foundry_docs/alder_creek_contract.md"},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides[require_api_user] = saved


def _configure_non_mock_environment(
    monkeypatch: pytest.MonkeyPatch, *, production: bool, live_foundry: bool
) -> None:
    values = {
        "APP_ENVIRONMENT": "production" if production else "development",
        "USE_LIVE_ISV_FOUNDRY": str(live_foundry).lower(),
        "USE_LIVE_ISV_FABRIC": "false",
        "USE_LIVE_ISV_WORK": "false",
        "USE_LIVE_ISV_WEB": "false",
        "AZURE_TENANT_ID": TENANT_ID,
        "API_AUDIENCE": AUDIENCE,
        "API_REQUIRED_SCOPE": "access_as_user",
        "ISV_SEARCH_ENDPOINT": "https://operator-search.example.com",
        "ISV_FOUNDRY_KB_NAME": "operator-kb",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    get_access_token_validator.cache_clear()


@pytest.mark.parametrize(
    ("production", "live_foundry"),
    [
        (True, False),
        (False, True),
    ],
)
def test_production_or_live_configuration_requires_bearer_authentication(
    monkeypatch: pytest.MonkeyPatch,
    production: bool,
    live_foundry: bool,
) -> None:
    saved = app.dependency_overrides.pop(require_api_user)
    try:
        _configure_non_mock_environment(
            monkeypatch,
            production=production,
            live_foundry=live_foundry,
        )
        client = TestClient(app)
        response = client.post(
            "/api/isv/ask",
            json={"question": "Assess renewal."},
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    finally:
        app.dependency_overrides[require_api_user] = saved
        get_settings.cache_clear()
        get_access_token_validator.cache_clear()


def test_mock_mode_rejects_a_non_bearer_authorization_header() -> None:
    saved = app.dependency_overrides.pop(require_api_user)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/isv/ask",
            headers={"Authorization": "Basic not-a-bearer-token"},
            json={"question": "Assess renewal."},
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides[require_api_user] = saved
