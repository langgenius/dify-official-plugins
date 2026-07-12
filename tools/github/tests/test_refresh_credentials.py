"""Unit tests for the GitHub OAuth refresh credentials method.

Covers four branches of ``GithubProvider._oauth_refresh_credentials``:

1. No ``refresh_token`` in credentials — return unchanged with
   ``expires_at=-1`` (backwards-compatible for classic OAuth Apps with
   non-expiring tokens, and for the non-OAuth ``credentials_for_provider``
   flow).
2. Successful refresh — return new ``access_tokens``, rotate the
   ``refresh_token`` if GitHub returned one, compute ``expires_at``
   from the response's ``expires_in`` field (minus a 60s safety margin).
3. Refresh failure (HTTP 400 or error body) — raise
   ``ToolProviderOAuthError`` so the framework surfaces a clear error
   instead of silently keeping a dead token.
4. Successful refresh with no ``expires_in`` in the response — treat the
   token as non-expiring (``expires_at=-1``), preserving backwards
   compatibility with OAuth Apps that don't expose the field.

All tests stub ``requests.post`` to avoid hitting the network.
"""

import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

# Pytest is not installed in this minimal environment; provide a minimal
# stand-in for the only feature we use (pytest.raises as a context manager).
class _Raises:
    def __init__(self, exc_type, match=None):
        self.exc_type = exc_type
        self.match = match

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(
                f"Expected {self.exc_type.__name__} to be raised, but no exception was."
            )
        if not issubclass(exc_type, self.exc_type):
            return False
        if self.match is not None and self.match not in str(exc):
            raise AssertionError(
                f"Expected exception message to match {self.match!r}, got: {exc}"
            )
        return True


class _PytestStub:
    def raises(self, exc_type, match=None):
        return _Raises(exc_type, match=match)


pytest = _PytestStub()


# Stub dify_plugin so the provider module imports without the SDK installed.
_fake_dify = types.ModuleType("dify_plugin")
_fake_oauth = types.ModuleType("dify_plugin.entities.oauth")


class _FakeToolOAuthCredentials:
    def __init__(self, credentials=None, expires_at=None):
        self.credentials = credentials or {}
        self.expires_at = expires_at


_fake_oauth.ToolOAuthCredentials = _FakeToolOAuthCredentials
_fake_errors = types.ModuleType("dify_plugin.errors.tool")


class _FakeToolProviderCredentialValidationError(Exception):
    pass


class _FakeToolProviderOAuthError(Exception):
    pass


_fake_errors.ToolProviderCredentialValidationError = _FakeToolProviderCredentialValidationError
_fake_errors.ToolProviderOAuthError = _FakeToolProviderOAuthError
_fake_dify.ToolProvider = type("ToolProvider", (), {})
_fake_dify.entities = types.ModuleType("dify_plugin.entities")
_fake_dify.entities.oauth = _fake_oauth
_fake_dify.errors = types.ModuleType("dify_plugin.errors")
_fake_dify.errors.tool = _fake_errors

sys.modules.setdefault("dify_plugin", _fake_dify)
sys.modules.setdefault("dify_plugin.entities", _fake_dify.entities)
sys.modules.setdefault("dify_plugin.entities.oauth", _fake_oauth)
sys.modules.setdefault("dify_plugin.errors", _fake_dify.errors)
sys.modules.setdefault("dify_plugin.errors.tool", _fake_errors)

# Add provider dir to path so `import provider.github` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "provider"))

from provider import github as github_module  # noqa: E402
from provider.github import GithubProvider  # noqa: E402


# --- helpers ----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or str(payload)

    def json(self):
        return self._payload


# --- _oauth_refresh_credentials branches ----------------------------------


def test_no_refresh_token_returns_credentials_unchanged_with_never_expires() -> None:
    """No refresh_token: return credentials unchanged with expires_at=-1."""
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old-token"}

    result = provider._oauth_refresh_credentials(
        redirect_uri="https://example.com/cb",
        system_credentials={"client_id": "cid", "client_secret": "csec"},
        credentials=credentials,
    )

    assert result.credentials == credentials
    assert result.expires_at == -1


def test_successful_refresh_returns_new_access_token_and_expires_at() -> None:
    """Successful refresh returns new access_tokens, optionally rotated refresh_token,
    and expires_at derived from expires_in minus a 60s safety margin.
    """
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {
        "access_tokens": "old-token",
        "refresh_token": "old-refresh",
    }
    new_payload = {
        "access_token": "new-token",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
    }
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(new_payload, 200)
    ), patch.object(github_module.time, "time", return_value=1_000_000):
        result = provider._oauth_refresh_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            credentials=credentials,
        )

    assert result.credentials["access_tokens"] == "new-token"
    assert result.credentials["refresh_token"] == "new-refresh"
    # expires_in=3600, safety_margin=60 -> expires_at = 1_000_000 + (3600 - 60) = 1_003_540
    assert result.expires_at == 1_003_540


def test_successful_refresh_without_new_refresh_token_keeps_old_one() -> None:
    """When GitHub does not rotate the refresh_token, keep the old one as fallback."""
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "old-refresh"}
    new_payload = {"access_token": "new-token", "expires_in": 7200}
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(new_payload, 200)
    ), patch.object(github_module.time, "time", return_value=1_000_000):
        result = provider._oauth_refresh_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            credentials=credentials,
        )

    assert result.credentials["access_tokens"] == "new-token"
    assert result.credentials["refresh_token"] == "old-refresh"


def test_successful_refresh_without_expires_in_returns_never_expires() -> None:
    """When GitHub does not return expires_in, treat as non-expiring (backwards compat)."""
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    new_payload = {"access_token": "new"}  # no expires_in
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(new_payload, 200)
    ):
        result = provider._oauth_refresh_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            credentials=credentials,
        )

    assert result.credentials["access_tokens"] == "new"
    assert result.expires_at == -1


def test_refresh_failure_http_400_raises_oauth_error() -> None:
    """HTTP 400 (revoked / invalid refresh_token) must surface as ToolProviderOAuthError."""
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    err_payload = {"error": "invalid_grant", "error_description": "token revoked"}
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(err_payload, 400, "bad")
    ):
        with pytest.raises(_FakeToolProviderOAuthError, match="token revoked"):
            provider._oauth_refresh_credentials(
                redirect_uri="https://example.com/cb",
                system_credentials={"client_id": "cid", "client_secret": "csec"},
                credentials=credentials,
            )


def test_refresh_failure_missing_access_token_raises_oauth_error() -> None:
    """200 response without access_token must raise (GitHub sometimes returns error bodies)."""
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    bad_payload = {"error": "temporarily_unavailable"}
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(bad_payload, 200)
    ):
        with pytest.raises(_FakeToolProviderOAuthError, match="temporarily_unavailable"):
            provider._oauth_refresh_credentials(
                redirect_uri="https://example.com/cb",
                system_credentials={"client_id": "cid", "client_secret": "csec"},
                credentials=credentials,
            )


def test_expires_in_smaller_than_safety_margin_floors_to_minimum_window() -> None:
    """Tiny expires_in (less than 60s safety) should still produce a positive expires_at.

    E.g. expires_in=5 means GitHub's token is already effectively expired;
    we floor to a 60s window so the framework has at least 1 minute to
    call the next refresh.
    """
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    new_payload = {"access_token": "new", "expires_in": 5}
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(new_payload, 200)
    ), patch.object(github_module.time, "time", return_value=1_000_000):
        result = provider._oauth_refresh_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            credentials=credentials,
        )

    # max(5 - 60, 60) + 1_000_000 = 60 + 1_000_000 = 1_000_060
    assert result.expires_at == 1_000_060
