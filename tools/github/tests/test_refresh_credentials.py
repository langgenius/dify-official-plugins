"""Unit tests for the GitHub OAuth refresh credentials method.

Covers the full surface of ``GithubProvider._oauth_refresh_credentials`` and
the initial-exchange surface of ``GithubProvider._oauth_get_credentials``:

1. No ``refresh_token`` in credentials — return unchanged with
   ``expires_at=-1`` (backwards-compatible for classic OAuth Apps with
   non-expiring tokens, and for the non-OAuth ``credentials_for_provider``
   flow).
2. Successful refresh — return new ``access_tokens``, rotate the
   ``refresh_token`` if GitHub returned one, compute ``expires_at``
   from the response's ``expires_in`` field (clamped to never exceed
   the real expiry).
3. Refresh failure (HTTP 400/502 with JSON OR HTML body) — raise
   ``ToolProviderOAuthError`` so the framework surfaces a clear error
   instead of silently keeping a dead token, and never raise
   ``JSONDecodeError`` from inside the provider.
4. Successful refresh with no ``expires_in`` in the response — treat the
   token as non-expiring (``expires_at=-1``), preserving backwards
   compatibility with OAuth Apps that don't expose the field.
5. Tiny ``expires_in`` (smaller than the safety margin) — clamp the
   safety buffer so the scheduled refresh does not fall after the
   token's real expiry.
6. ``expires_in=0`` — signal ``expires_at=-1`` for an immediate refresh.
7. ``_oauth_get_credentials`` persists ``refresh_token`` and
   ``expires_in`` from the initial exchange so the refresh code path
   is reachable.
8. ``_oauth_get_credentials`` without ``refresh_token`` keeps the
   legacy single-key credentials shape and ``expires_at=-1``.

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
_fake_requests = types.ModuleType("requests")


class _FakeRequestsPost:
    def __call__(self, *args, **kwargs):  # pragma: no cover - never used directly
        raise RuntimeError("requests.post was not stubbed in this test")


_fake_requests.post = _FakeRequestsPost()  # type: ignore[attr-defined]
sys.modules.setdefault("requests", _fake_requests)

_fake_werkzeug = types.ModuleType("werkzeug")


class _FakeWerkzeugRequest:
    def __init__(self, *args, **kwargs):
        pass


_fake_werkzeug.Request = _FakeWerkzeugRequest  # type: ignore[attr-defined]
sys.modules.setdefault("werkzeug", _fake_werkzeug)

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
    and expires_at computed from expires_in with a clamped safety buffer.
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
    # expires_in=3600 -> safety = min(60, max(3600 - 1, 0)) = 60
    # expires_at = 1_000_000 + 60 = 1_000_060
    assert result.expires_at == 1_000_060


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


def test_expires_in_smaller_than_safety_margin_clamps_to_real_expiry() -> None:
    """Tiny expires_in must clamp the safety buffer so the scheduled refresh
    never falls after the token's real expiry.

    E.g. expires_in=5 means GitHub's token is already effectively expired.
    With the old formula (max(int(expires_in) - 60, 60) + now) we would have
    scheduled the refresh 60s in the future — but the token expired 55s ago.
    The new formula picks min(60, max(int(expires_in) - 1, 0)) = 4 and
    schedules a refresh 4s out, before the token is fully stale.
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

    # min(60, max(5 - 1, 0)) + 1_000_000 = 4 + 1_000_000 = 1_000_004
    assert result.expires_at == 1_000_004


def test_expires_in_zero_signals_immediate_refresh() -> None:
    """When GitHub returns expires_in=0 the token is already expired; we
    must return expires_at=-1 so the framework refreshes immediately rather
    than scheduling the refresh at a stale `now + 0` timestamp.
    """
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    new_payload = {"access_token": "new", "expires_in": 0}
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(new_payload, 200)
    ):
        result = provider._oauth_refresh_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            credentials=credentials,
        )

    assert result.expires_at == -1


class _HtmlResponse(_FakeResponse):
    """A non-JSON body that returns HTML when .json() is called."""

    def __init__(self, status_code: int, body: str):
        super().__init__(payload=None, status_code=status_code, text=body)

    def json(self):
        raise ValueError(f"Expecting value: line 1 column 1 (char 0) — body={self.text!r}")


def test_refresh_failure_http_400_with_html_body_surfaces_snippet() -> None:
    """An HTTP 400 with an HTML error page must surface as ToolProviderOAuthError
    with the response status + a snippet of the body — not a JSONDecodeError.
    """
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    html = "<html><body>400 Bad Request — nginx</body></html>"
    with patch.object(
        github_module.requests, "post",
        return_value=_HtmlResponse(400, html),
    ):
        with pytest.raises(_FakeToolProviderOAuthError, match="nginx"):
            provider._oauth_refresh_credentials(
                redirect_uri="https://example.com/cb",
                system_credentials={"client_id": "cid", "client_secret": "csec"},
                credentials=credentials,
            )


def test_refresh_failure_http_502_with_empty_body_surfaces_snippet() -> None:
    """An HTTP 502 with an empty body must surface as ToolProviderOAuthError
    instead of raising a JSONDecodeError or returning silently.
    """
    provider = GithubProvider.__new__(GithubProvider)
    credentials = {"access_tokens": "old", "refresh_token": "r"}
    with patch.object(
        github_module.requests, "post",
        return_value=_HtmlResponse(502, ""),
    ):
        with pytest.raises(_FakeToolProviderOAuthError, match="GitHub OAuth refresh failed"):
            provider._oauth_refresh_credentials(
                redirect_uri="https://example.com/cb",
                system_credentials={"client_id": "cid", "client_secret": "csec"},
                credentials=credentials,
            )


class _WerkzeugRequestStub:
    """Minimal stand-in for werkzeug.Request used by _oauth_get_credentials."""

    def __init__(self, args):
        self.args = args


def test_initial_auth_persists_refresh_token_and_expires_in() -> None:
    """`_oauth_get_credentials` must persist `refresh_token` and `expires_in`
    alongside `access_tokens`, otherwise the refresh code path added in this
    PR is unreachable for users who authenticate via a GitHub OAuth App that
    actually issues refresh tokens.
    """
    provider = GithubProvider.__new__(GithubProvider)
    payload = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
        "scope": "read:user",
        "token_type": "bearer",
    }
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(payload, 200)
    ), patch.object(github_module.time, "time", return_value=2_000_000):
        result = provider._oauth_get_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            request=_WerkzeugRequestStub({"code": "abc123"}),
        )

    assert result.credentials["access_tokens"] == "new-access"
    assert result.credentials["refresh_token"] == "new-refresh"
    assert result.credentials["expires_in"] == 3600
    # expires_at = now + expires_in - 60 = 2_000_000 + 3600 - 60 = 2_003_540
    assert result.expires_at == 2_003_540


def test_initial_auth_without_refresh_token_keeps_legacy_behaviour() -> None:
    """When the OAuth response omits `refresh_token` (classic OAuth App
    without refresh-token support), `_oauth_get_credentials` must NOT
    invent a key — only `access_tokens` should be present, and
    `expires_at` should fall back to -1 (never expires).
    """
    provider = GithubProvider.__new__(GithubProvider)
    payload = {"access_token": "new-access"}  # no refresh_token, no expires_in
    with patch.object(
        github_module.requests, "post", return_value=_FakeResponse(payload, 200)
    ):
        result = provider._oauth_get_credentials(
            redirect_uri="https://example.com/cb",
            system_credentials={"client_id": "cid", "client_secret": "csec"},
            request=_WerkzeugRequestStub({"code": "abc123"}),
        )

    assert result.credentials == {"access_tokens": "new-access"}
    assert result.expires_at == -1
