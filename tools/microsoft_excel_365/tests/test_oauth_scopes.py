from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import provider.microsoft_excel365 as excel_module
from dify_plugin.errors.tool import (
    ToolProviderCredentialValidationError,
    ToolProviderOAuthError,
)
from provider.microsoft_excel365 import Excel365Provider


# Every scope the tools rely on at runtime, restated independently of the provider so
# that changing `_SCOPES` is a deliberate act. A missing scope means Graph rejects the
# call at runtime; a scope that the Azure app registration never had consented is what
# makes Entra ID show a consent screen again.
EXPECTED_SCOPES = {
    "offline_access",
    "User.Read",
    "Files.ReadWrite",
    "Files.ReadWrite.All",
    "Sites.Read.All",
}

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload


def test_expected_scopes_matches_the_provider() -> None:
    assert set(Excel365Provider._SCOPES.split()) == EXPECTED_SCOPES, (
        "The scopes requested by the provider changed. If that is intentional, update "
        "EXPECTED_SCOPES, the setup steps in README.md and the scope list in PRIVACY.md."
    )


def test_authorization_url_requests_every_required_scope() -> None:
    provider = Excel365Provider()

    url = provider._oauth_get_authorization_url(
        "https://example.com/callback",
        {"client_id": "client-id"},
    )

    parsed = urlparse(url)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/common/oauth2/v2.0/authorize"

    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["https://example.com/callback"]
    assert set(query["scope"][0].split()) == EXPECTED_SCOPES


def test_token_exchange_requests_the_full_scope_set(monkeypatch) -> None:
    provider = Excel365Provider()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data))
        return FakeResponse(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(excel_module.requests, "post", fake_post)

    credentials = provider._oauth_get_credentials(
        "https://example.com/callback",
        {"client_id": "client-id", "client_secret": "client-secret"},
        SimpleNamespace(args={"code": "auth-code"}),
    )

    assert calls[0][0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert set(calls[0][1]["scope"].split()) == EXPECTED_SCOPES
    assert credentials.credentials["access_token"] == "access-token"
    assert credentials.credentials["refresh_token"] == "refresh-token"


def test_token_exchange_requires_authorization_code(monkeypatch) -> None:
    provider = Excel365Provider()

    def fail_post(*args, **kwargs):
        raise AssertionError("the token endpoint must not be called without a code")

    monkeypatch.setattr(excel_module.requests, "post", fail_post)

    with pytest.raises(ToolProviderOAuthError):
        provider._oauth_get_credentials(
            "https://example.com/callback",
            {"client_id": "client-id", "client_secret": "client-secret"},
            SimpleNamespace(args={}),
        )


def test_refresh_does_not_narrow_or_widen_the_granted_scopes(monkeypatch) -> None:
    provider = Excel365Provider()
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append((url, data))
        return FakeResponse({"access_token": "new-access-token", "expires_in": 3600})

    monkeypatch.setattr(excel_module.requests, "post", fake_post)

    credentials = provider._oauth_refresh_credentials(
        "https://example.com/callback",
        {"client_id": "client-id", "client_secret": "client-secret"},
        {"refresh_token": "old-refresh-token"},
    )

    assert calls[0][1]["grant_type"] == "refresh_token"
    # The refresh leg must not carry `scope`: it may only be equivalent to or a subset
    # of the original authorization request, so sending the current set would break
    # connections authorized before a scope was added.
    assert "scope" not in calls[0][1]
    # Microsoft does not always return a new refresh token, keep the existing one.
    assert credentials.credentials["refresh_token"] == "old-refresh-token"


def test_validate_credentials_calls_the_me_endpoint(monkeypatch) -> None:
    provider = Excel365Provider()
    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers))
        return FakeResponse({"displayName": "Ada Lovelace"})

    monkeypatch.setattr(excel_module.requests, "get", fake_get)

    provider._validate_credentials({"access_token": "access-token"})

    # `GET /me` needs User.Read, which is why it has to be part of _SCOPES.
    assert calls[0][0] == "https://graph.microsoft.com/v1.0/me"
    assert calls[0][1]["Authorization"] == "Bearer access-token"


def test_validate_credentials_rejects_missing_access_token() -> None:
    provider = Excel365Provider()

    with pytest.raises(ToolProviderCredentialValidationError):
        provider._validate_credentials({})


def test_validate_credentials_surfaces_insufficient_permissions(monkeypatch) -> None:
    provider = Excel365Provider()

    def fake_get(url, headers, timeout):
        return FakeResponse({}, status_code=403, text="Insufficient privileges")

    monkeypatch.setattr(excel_module.requests, "get", fake_get)

    # The matched text is the fake response body, not provider wording.
    with pytest.raises(
        ToolProviderCredentialValidationError, match="Insufficient privileges"
    ):
        provider._validate_credentials({"access_token": "access-token"})


@pytest.mark.parametrize("document", ["README.md", "PRIVACY.md"])
def test_documentation_lists_every_requested_scope(document: str) -> None:
    content = (PLUGIN_ROOT / document).read_text(encoding="utf-8")

    # Derived from the provider so the setup instructions and the published privacy
    # policy cannot drift away from the scopes that are actually requested.
    for scope in Excel365Provider._SCOPES.split():
        assert (
            f"`{scope}`" in content
        ), f"{scope} is requested by the provider but not documented in {document}"
