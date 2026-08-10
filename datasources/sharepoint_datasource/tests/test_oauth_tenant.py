from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import provider.sharepoint as sharepoint_module
from dify_plugin.errors.tool import DatasourceOAuthError
from provider.sharepoint import SharePointDatasourceProvider


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise sharepoint_module.requests.HTTPError(self.text)


def test_default_tenant_is_organizations() -> None:
    provider = SharePointDatasourceProvider()

    tenant_id = provider._get_tenant_id_for_auth({})

    assert tenant_id == "organizations"
    assert (
        urlparse(provider._get_auth_url(tenant_id)).path
        == "/organizations/oauth2/v2.0/authorize"
    )


def test_tenant_values_generate_expected_authorize_and_token_urls() -> None:
    provider = SharePointDatasourceProvider()

    assert urlparse(provider._get_auth_url("common")).path == "/common/oauth2/v2.0/authorize"
    assert (
        urlparse(provider._get_token_url("organizations")).path
        == "/organizations/oauth2/v2.0/token"
    )
    assert (
        urlparse(provider._get_token_url("contoso.onmicrosoft.com")).path
        == "/contoso.onmicrosoft.com/oauth2/v2.0/token"
    )


def test_tenant_path_is_stripped_and_quoted() -> None:
    provider = SharePointDatasourceProvider()

    assert (
        urlparse(provider._get_auth_url(" tenant/with/slash ")).path
        == "/tenant%2Fwith%2Fslash/oauth2/v2.0/authorize"
    )


def test_refresh_uses_saved_tenant() -> None:
    provider = SharePointDatasourceProvider()

    assert (
        provider._get_tenant_id_for_token({"tenant_id": "contoso.onmicrosoft.com"})
        == "contoso.onmicrosoft.com"
    )


def test_refresh_falls_back_to_system_tenant_for_legacy_credentials() -> None:
    provider = SharePointDatasourceProvider()

    assert (
        provider._get_tenant_id_for_token({}, {"tenant_id": "contoso.onmicrosoft.com"})
        == "contoso.onmicrosoft.com"
    )


def test_get_credentials_saves_tenant_and_refresh_token(monkeypatch) -> None:
    provider = SharePointDatasourceProvider()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return FakeResponse(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        )

    def fake_get(url, headers, timeout):
        return FakeResponse({"displayName": "Ada Lovelace", "userPrincipalName": "ada@example.com"})

    monkeypatch.setattr(sharepoint_module.time, "time", lambda: 1000)
    monkeypatch.setattr(sharepoint_module.requests, "post", fake_post)
    monkeypatch.setattr(sharepoint_module.requests, "get", fake_get)

    credentials = provider._oauth_get_credentials(
        "https://example.com/callback",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "subdomain": "contoso",
            "tenant_id": "contoso.onmicrosoft.com",
        },
        SimpleNamespace(args={"code": "auth-code", "state": "state"}),
    )

    assert (
        calls[0][0]
        == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    )
    assert credentials.expires_at == 4600
    assert credentials.credentials["tenant_id"] == "contoso.onmicrosoft.com"
    assert credentials.credentials["refresh_token"] == "refresh-token"


def test_get_credentials_requires_refresh_token(monkeypatch) -> None:
    provider = SharePointDatasourceProvider()

    def fake_post(url, data, headers, timeout):
        return FakeResponse({"access_token": "access-token", "expires_in": 3600})

    monkeypatch.setattr(sharepoint_module.requests, "post", fake_post)

    with pytest.raises(DatasourceOAuthError, match="refresh_token"):
        provider._oauth_get_credentials(
            "https://example.com/callback",
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "subdomain": "contoso",
                "tenant_id": "organizations",
            },
            SimpleNamespace(args={"code": "auth-code", "state": "state"}),
        )


def test_refresh_uses_saved_tenant_and_rotates_refresh_token(monkeypatch) -> None:
    provider = SharePointDatasourceProvider()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return FakeResponse(
            {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 120,
            }
        )

    def fake_get(url, headers, timeout):
        return FakeResponse({"displayName": "Ada Lovelace", "userPrincipalName": "ada@example.com"})

    monkeypatch.setattr(sharepoint_module.time, "time", lambda: 1000)
    monkeypatch.setattr(sharepoint_module.requests, "post", fake_post)
    monkeypatch.setattr(sharepoint_module.requests, "get", fake_get)

    credentials = provider._oauth_refresh_credentials(
        "https://example.com/callback",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "subdomain": "contoso",
            "tenant_id": "organizations",
        },
        {
            "refresh_token": "old-refresh-token",
            "subdomain": "contoso",
            "tenant_id": "common",
        },
    )

    assert calls[0][0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert credentials.expires_at == 1120
    assert credentials.credentials["tenant_id"] == "common"
    assert credentials.credentials["refresh_token"] == "new-refresh-token"
