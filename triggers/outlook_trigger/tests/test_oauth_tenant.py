from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import provider.outlook as outlook_module
from dify_plugin.errors.trigger import TriggerProviderOAuthError
from provider.outlook import OutlookSubscriptionConstructor


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload


def test_authorization_url_defaults_to_organizations(monkeypatch) -> None:
    constructor = OutlookSubscriptionConstructor(None)
    monkeypatch.setattr(constructor, "_store_oauth_state", lambda redirect_uri, state: None)

    url = constructor._oauth_get_authorization_url(
        "https://example.com/callback",
        {"client_id": "client-id"},
    )

    assert urlparse(url).path == "/organizations/oauth2/v2.0/authorize"


def test_get_credentials_saves_tenant(monkeypatch) -> None:
    constructor = OutlookSubscriptionConstructor(None)
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return FakeResponse(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 0,
            }
        )

    monkeypatch.setattr(constructor, "_validate_oauth_state", lambda redirect_uri, state: None)
    monkeypatch.setattr(outlook_module.time, "time", lambda: 1000)
    monkeypatch.setattr(outlook_module.requests, "post", fake_post)

    credentials = constructor._oauth_get_credentials(
        "https://example.com/callback",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "tenant_id": "contoso.onmicrosoft.com",
        },
        SimpleNamespace(args={"code": "auth-code", "state": "state"}),
    )

    assert (
        calls[0][0]
        == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    )
    assert credentials.expires_at == 1000
    assert credentials.credentials["tenant_id"] == "contoso.onmicrosoft.com"
    assert credentials.credentials["refresh_token"] == "refresh-token"


def test_refresh_uses_saved_tenant(monkeypatch) -> None:
    constructor = OutlookSubscriptionConstructor(None)
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return FakeResponse({"access_token": "new-access-token", "expires_in": 0})

    monkeypatch.setattr(outlook_module.time, "time", lambda: 1000)
    monkeypatch.setattr(outlook_module.requests, "post", fake_post)

    credentials = constructor._oauth_refresh_credentials(
        "https://example.com/callback",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "tenant_id": "organizations",
        },
        {
            "refresh_token": "old-refresh-token",
            "tenant_id": "common",
        },
    )

    assert calls[0][0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert credentials.expires_at == 1000
    assert credentials.credentials["tenant_id"] == "common"
    assert credentials.credentials["refresh_token"] == "old-refresh-token"


def test_refresh_falls_back_to_system_tenant_for_legacy_credentials(monkeypatch) -> None:
    constructor = OutlookSubscriptionConstructor(None)
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return FakeResponse({"access_token": "new-access-token", "expires_in": 120})

    monkeypatch.setattr(outlook_module.time, "time", lambda: 1000)
    monkeypatch.setattr(outlook_module.requests, "post", fake_post)

    credentials = constructor._oauth_refresh_credentials(
        "https://example.com/callback",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "tenant_id": "contoso.onmicrosoft.com",
        },
        {"refresh_token": "old-refresh-token"},
    )

    assert (
        calls[0][0]
        == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    )
    assert credentials.credentials["tenant_id"] == "contoso.onmicrosoft.com"


def test_refresh_requires_system_client_secret(monkeypatch) -> None:
    constructor = OutlookSubscriptionConstructor(None)

    def fake_post(url, data, headers, timeout):
        raise AssertionError("refresh should fail before the token request")

    monkeypatch.setattr(outlook_module.requests, "post", fake_post)

    with pytest.raises(TriggerProviderOAuthError, match="Client ID or Client Secret"):
        constructor._oauth_refresh_credentials(
            "https://example.com/callback",
            {"client_id": "client-id"},
            {"refresh_token": "old-refresh-token"},
        )
