import secrets
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request

from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError


class GithubProvider(ToolProvider):
    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _API_USER_URL = "https://api.github.com/user"

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate the authorization URL for the Github OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": system_credentials.get("scope", "read:user repo"),
            "state": state,
            # Optionally: allow_signup, login, etc.
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange code for access_token.
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No code provided")
        # Optionally: validate state here

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json"}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)
        response_json = response.json()
        access_tokens = response_json.get("access_token")
        if not access_tokens:
            raise ToolProviderOAuthError(f"Error in GitHub OAuth: {response_json}")

        # Persist refresh_token + expires_in alongside access_tokens so that
        # the framework's later call to _oauth_refresh_credentials has the
        # information it needs. Without this, refresh_token is silently
        # dropped and the refresh code path is unreachable even when the
        # GitHub OAuth App is configured to issue refresh tokens.
        credentials: dict[str, Any] = {"access_tokens": access_tokens}
        refresh_token = response_json.get("refresh_token")
        if refresh_token:
            credentials["refresh_token"] = refresh_token
        expires_in = response_json.get("expires_in")
        if expires_in is not None:
            try:
                credentials["expires_in"] = int(expires_in)
                expires_at = int(expires_in) - 60 + int(time.time())
            except (TypeError, ValueError):
                expires_at = -1
        else:
            expires_at = -1

        return ToolOAuthCredentials(credentials=credentials, expires_at=expires_at)

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        """
        Refresh the GitHub OAuth access token via GitHub's token endpoint.

        GitHub's OAuth Apps issue refresh tokens only when the app is configured
        to allow it (newer GitHub Apps default behavior). If no refresh_token
        is present (classic OAuth Apps with non-expiring tokens, or the
        ``credentials_for_provider`` flow that bypasses OAuth), return
        credentials unchanged with ``expires_at=-1`` to signal "never expires" —
        this preserves backwards compatibility.
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            # No refresh token available: token does not expire. Pass through.
            return ToolOAuthCredentials(credentials=credentials, expires_at=-1)

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Accept": "application/json"}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)

        # Surface non-2xx responses as ToolProviderOAuthError without first
        # attempting to parse the body as JSON — a Cloudflare 5xx HTML page
        # or a network-level 502 should not raise a JSONDecodeError. When the
        # body IS valid JSON, prefer the structured error fields; otherwise
        # fall back to a status-and-snippet message.
        if response.status_code >= 400:
            try:
                error_body = response.json()
            except ValueError:
                error_body = None
            detail = (
                (error_body or {}).get("error_description")
                or (error_body or {}).get("error")
                or response.text[:200].strip()
            )
            raise ToolProviderOAuthError(f"GitHub OAuth refresh failed: {detail}")

        # Status was 2xx; parse the JSON body. If GitHub somehow returned a
        # non-JSON success body (e.g. proxy HTML page), surface that as a
        # provider error rather than letting the AttributeError on .get()
        # propagate.
        try:
            response_json = response.json()
        except ValueError:
            raise ToolProviderOAuthError(
                f"GitHub OAuth refresh returned a non-JSON success body: "
                f"status={response.status_code} body={response.text[:200].strip()!r}"
            )
        if not isinstance(response_json, dict) or "access_token" not in response_json:
            raise ToolProviderOAuthError(
                f"GitHub OAuth refresh response missing access_token: "
                f"{response.text[:200].strip()!r}"
            )

        new_credentials = {
            "access_tokens": response_json["access_token"],
            # GitHub may rotate the refresh token; keep the new one if returned,
            # else keep the previous refresh_token as a fallback.
            "refresh_token": response_json.get("refresh_token", refresh_token),
        }
        expires_in = response_json.get("expires_in")
        if expires_in is None:
            # No expiry — backwards-compatible with non-expiring OAuth Apps.
            expires_at = -1
        else:
            # Clamp the safety buffer so we never schedule a refresh after the
            # token's real expiry. expires_in=5 (or any value smaller than the
            # 60s buffer) means the token is effectively expired: schedule an
            # immediate refresh instead of pretending we still have 60 seconds.
            now = int(time.time())
            safety = min(60, max(int(expires_in) - 1, 0))
            expires_at = now + safety if safety > 0 else -1

        return ToolOAuthCredentials(credentials=new_credentials, expires_at=expires_at)

    def _validate_credentials(self, credentials: dict) -> None:
        try:
            if "access_tokens" not in credentials or not credentials.get("access_tokens"):
                raise ToolProviderCredentialValidationError("GitHub API Access Token is required.")
            headers = {
                "Authorization": f"Bearer {credentials['access_tokens']}",
                "Accept": "application/vnd.github+json",
            }
            response = requests.get(self._API_USER_URL, headers=headers, timeout=10)
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError(response.json().get("message"))
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
