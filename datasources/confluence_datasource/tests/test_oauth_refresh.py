from types import SimpleNamespace

import pytest
import provider.confluence_datasource as confluence_module
from dify_plugin.errors.tool import DatasourceOAuthError
from provider.confluence_datasource import ConfluenceDatasourceProvider

NOW = 1_700_000_000
SYSTEM_CREDENTIALS = {"client_id": "client-id", "client_secret": "client-secret"}
STORED_CREDENTIALS = {
    "access_token": "old-access",
    "refresh_token": "old-refresh",
    "workspace_id": "cloud-id",
    "workspace_name": "Example",
    "workspace_icon": "https://example.atlassian.net",
}


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(confluence_module.time, "time", lambda: NOW)


def _stub_token_endpoint(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> dict:
    captured = {}

    def fake_post(url, data, timeout):
        captured["url"] = url
        captured["data"] = data
        return response

    monkeypatch.setattr(confluence_module.requests, "post", fake_post)
    return captured


def test_refresh_sets_expires_at_from_expires_in(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a refresh that drops expires_at stores -1, which Dify treats as
    # "never expires", so the token is never refreshed again and dies an hour later.
    captured = _stub_token_endpoint(
        monkeypatch,
        FakeResponse({"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}),
    )

    result = ConfluenceDatasourceProvider()._oauth_refresh_credentials(
        "https://example.com/callback", SYSTEM_CREDENTIALS, STORED_CREDENTIALS
    )

    assert result.expires_at == NOW + 3600
    assert result.credentials["access_token"] == "new-access"
    assert result.credentials["refresh_token"] == "new-refresh"
    assert result.credentials["workspace_id"] == "cloud-id"
    assert result.name == "Example"
    assert captured["url"] == ConfluenceDatasourceProvider._TOKEN_URL
    assert captured["data"]["grant_type"] == "refresh_token"
    assert captured["data"]["refresh_token"] == "old-refresh"


def test_refresh_keeps_refresh_token_when_not_rotated(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_token_endpoint(monkeypatch, FakeResponse({"access_token": "new-access", "expires_in": 3600}))

    result = ConfluenceDatasourceProvider()._oauth_refresh_credentials(
        "https://example.com/callback", SYSTEM_CREDENTIALS, STORED_CREDENTIALS
    )

    assert result.credentials["refresh_token"] == "old-refresh"
    assert result.expires_at == NOW + 3600


def test_refresh_without_expires_in_is_non_expiring(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_token_endpoint(monkeypatch, FakeResponse({"access_token": "new-access"}))

    result = ConfluenceDatasourceProvider()._oauth_refresh_credentials(
        "https://example.com/callback", SYSTEM_CREDENTIALS, STORED_CREDENTIALS
    )

    assert result.expires_at == -1


def test_refresh_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_token_endpoint(monkeypatch, FakeResponse({}, status_code=400, text="invalid_grant"))

    with pytest.raises(DatasourceOAuthError, match="400"):
        ConfluenceDatasourceProvider()._oauth_refresh_credentials(
            "https://example.com/callback", SYSTEM_CREDENTIALS, STORED_CREDENTIALS
        )


def test_authorization_sets_expires_at_from_expires_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_token_endpoint(
        monkeypatch,
        FakeResponse({"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}),
    )
    monkeypatch.setattr(
        confluence_module.requests,
        "get",
        lambda url, headers, timeout: FakeResponse(
            [{"id": "cloud-id", "name": "Example", "url": "https://example.atlassian.net"}]
        ),
    )

    result = ConfluenceDatasourceProvider()._oauth_get_credentials(
        "https://example.com/callback", SYSTEM_CREDENTIALS, SimpleNamespace(args={"code": "auth-code"})
    )

    assert result.expires_at == NOW + 3600
    assert result.credentials["refresh_token"] == "refresh"
    assert result.credentials["workspace_id"] == "cloud-id"
