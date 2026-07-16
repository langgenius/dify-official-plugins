from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import provider.onedrive as onedrive_module
from dify_plugin.errors.tool import DatasourceOAuthError
from provider.onedrive import OneDriveDatasourceProvider


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload


def test_authorization_url_defaults_to_organizations() -> None:
    provider = OneDriveDatasourceProvider()

    url = provider._oauth_get_authorization_url(
        "https://example.com/callback",
        {"client_id": "client-id"},
    )

    parsed = urlparse(url)
    assert parsed.path == "/organizations/oauth2/v2.0/authorize"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client-id"]
    assert query["scope"] == ["offline_access User.Read Files.Read Files.Read.All"]


def test_authorization_url_accepts_common_and_quotes_tenant_path() -> None:
    provider = OneDriveDatasourceProvider()

    common_url = provider._oauth_get_authorization_url(
        "https://example.com/callback",
        {"client_id": "client-id", "tenant_id": "common"},
    )
    quoted_url = provider._oauth_get_authorization_url(
        "https://example.com/callback",
        {"client_id": "client-id", "tenant_id": " tenant/with/slash "},
    )

    assert urlparse(common_url).path == "/common/oauth2/v2.0/authorize"
    assert urlparse(quoted_url).path == "/tenant%2Fwith%2Fslash/oauth2/v2.0/authorize"


def test_expires_at_handles_zero_and_missing_expires_in(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()
    monkeypatch.setattr(onedrive_module.time, "time", lambda: 1000)

    assert provider._expires_at(0) == 1000
    assert provider._expires_at(None) == 4540


def test_get_credentials_saves_tenant_refresh_token_and_expiry(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()
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

    def fake_get(url, headers, timeout):
        return FakeResponse({"displayName": "Ada Lovelace", "userPrincipalName": "ada@example.com"})

    monkeypatch.setattr(onedrive_module.time, "time", lambda: 1000)
    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)
    monkeypatch.setattr(onedrive_module.requests, "get", fake_get)

    credentials = provider._oauth_get_credentials(
        "https://example.com/callback",
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "tenant_id": "contoso.onmicrosoft.com",
        },
        SimpleNamespace(args={"code": "auth-code"}),
    )

    assert (
        calls[0][0]
        == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    )
    assert credentials.name == "Ada Lovelace"
    assert credentials.expires_at == 1000
    assert credentials.credentials["tenant_id"] == "contoso.onmicrosoft.com"
    assert credentials.credentials["access_token"] == "access-token"
    assert credentials.credentials["refresh_token"] == "refresh-token"


def test_get_credentials_requires_refresh_token(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()

    def fake_post(url, data, headers, timeout):
        return FakeResponse({"access_token": "access-token", "expires_in": 3600})

    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)

    with pytest.raises(DatasourceOAuthError, match="refresh_token"):
        provider._oauth_get_credentials(
            "https://example.com/callback",
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "tenant_id": "organizations",
            },
            SimpleNamespace(args={"code": "auth-code"}),
        )


def test_get_credentials_wraps_token_request_error(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()

    def fake_post(url, data, headers, timeout):
        raise onedrive_module.requests.RequestException("network down")

    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)

    with pytest.raises(DatasourceOAuthError, match="token exchange"):
        provider._oauth_get_credentials(
            "https://example.com/callback",
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "tenant_id": "organizations",
            },
            SimpleNamespace(args={"code": "auth-code"}),
        )


def test_get_credentials_wraps_userinfo_request_error(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()

    def fake_post(url, data, headers, timeout):
        return FakeResponse(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
            }
        )

    def fake_get(url, headers, timeout):
        raise onedrive_module.requests.RequestException("network down")

    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)
    monkeypatch.setattr(onedrive_module.requests, "get", fake_get)

    with pytest.raises(DatasourceOAuthError, match="userinfo"):
        provider._oauth_get_credentials(
            "https://example.com/callback",
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "tenant_id": "organizations",
            },
            SimpleNamespace(args={"code": "auth-code"}),
        )


def test_refresh_credentials_uses_saved_tenant_and_replaces_refresh_token(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()
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

    monkeypatch.setattr(onedrive_module.time, "time", lambda: 1000)
    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)

    credentials = provider._oauth_refresh_credentials(
        "https://example.com/callback",
        {"client_id": "client-id", "client_secret": "client-secret"},
        {
            "refresh_token": "old-refresh-token",
            "tenant_id": "common",
            "user_email": "ada@example.com",
        },
    )

    assert calls[0][0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert calls[0][1]["grant_type"] == "refresh_token"
    assert credentials.expires_at == 1060
    assert credentials.credentials["refresh_token"] == "new-refresh-token"
    assert credentials.credentials["tenant_id"] == "common"


def test_refresh_credentials_keeps_existing_refresh_token_when_not_returned(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()

    def fake_post(url, data, headers, timeout):
        return FakeResponse({"access_token": "new-access-token", "expires_in": 0})

    monkeypatch.setattr(onedrive_module.time, "time", lambda: 1000)
    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)

    credentials = provider._oauth_refresh_credentials(
        "https://example.com/callback",
        {"client_id": "client-id", "client_secret": "client-secret"},
        {"refresh_token": "old-refresh-token", "tenant_id": "organizations"},
    )

    assert credentials.credentials["refresh_token"] == "old-refresh-token"
    assert credentials.credentials["tenant_id"] == "organizations"
    assert credentials.expires_at == 1000


def test_refresh_credentials_falls_back_to_system_tenant_for_legacy_credentials(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data, headers, timeout))
        return FakeResponse({"access_token": "new-access-token"})

    monkeypatch.setattr(onedrive_module.time, "time", lambda: 1000)
    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)

    credentials = provider._oauth_refresh_credentials(
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
    assert credentials.expires_at == 4540


def test_refresh_credentials_wraps_token_request_error(monkeypatch) -> None:
    provider = OneDriveDatasourceProvider()

    def fake_post(url, data, headers, timeout):
        raise onedrive_module.requests.RequestException("network down")

    monkeypatch.setattr(onedrive_module.requests, "post", fake_post)

    with pytest.raises(DatasourceOAuthError, match="token refresh"):
        provider._oauth_refresh_credentials(
            "https://example.com/callback",
            {"client_id": "client-id", "client_secret": "client-secret"},
            {"refresh_token": "old-refresh-token", "tenant_id": "organizations"},
        )


def test_refresh_credentials_requires_system_client_secret() -> None:
    provider = OneDriveDatasourceProvider()

    with pytest.raises(DatasourceOAuthError, match="client_id or client_secret"):
        provider._oauth_refresh_credentials(
            "https://example.com/callback",
            {"client_id": "client-id"},
            {
                "refresh_token": "old-refresh-token",
                "client_secret": "credential-secret",
                "tenant_id": "organizations",
            },
        )
