import secrets
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError
from werkzeug import Request

from tools.google_client import is_per_user
from tools.user_auth import AUTHORIZE_URL, SCOPE, TOKEN_URL


class GoogleDocsProvider(ToolProvider):
    """Google Docs through a Google sign-in from the Dify console (OAuth), or each chat user signing in."""

    # ── OAuth ──────────────────────────────────────────────────────────

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "response_type": "code",
            # offline + consent: Google only returns a refresh token on a consented, offline sign-in.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": secrets.token_urlsafe(16),
        }
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        if request.args.get("error"):
            raise ToolProviderOAuthError(f"Google sign-in failed: {request.args['error']}")
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No authorization code provided.")
        payload = self._token_request({
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })
        return self._credentials(payload)

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available; authorize the plugin again.")
        payload = self._token_request({
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        # Google returns a refresh token on the first exchange only.
        payload.setdefault("refresh_token", refresh_token)
        return self._credentials(payload)

    @staticmethod
    def _token_request(data: Mapping[str, str]) -> dict[str, Any]:
        try:
            response = requests.post(TOKEN_URL, data=data, timeout=30)
        except requests.exceptions.RequestException as e:
            raise ToolProviderOAuthError(f"Could not reach Google: {e}") from e
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200 or not payload.get("access_token"):
            detail = payload.get("error_description") or payload.get("error") or response.text[:300]
            raise ToolProviderOAuthError(f"Google sign-in failed ({response.status_code}): {detail}")
        return payload

    @staticmethod
    def _credentials(payload: Mapping[str, Any]) -> ToolOAuthCredentials:
        return ToolOAuthCredentials(
            credentials={"access_token": payload["access_token"], "refresh_token": payload.get("refresh_token", "")},
            expires_at=int(time.time()) + int(payload.get("expires_in", 3599)),
        )

    # ── validation ─────────────────────────────────────────────────────

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if is_per_user(credentials):
            self._validate_per_user(credentials)
            return
        token = credentials.get("access_token")
        if not token:
            raise ToolProviderCredentialValidationError("Google Docs access token is required; authorize the plugin.")
        try:
            response = requests.get(
                "https://www.googleapis.com/drive/v3/about", params={"fields": "user(emailAddress)"},
                headers={"Authorization": f"Bearer {token}"}, timeout=30,
            )
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Could not reach Google Docs: {e}") from e
        if response.status_code == 401:
            raise ToolProviderCredentialValidationError("The access token is invalid or expired; authorize the plugin again.")
        if response.status_code == 403:
            raise ToolProviderCredentialValidationError(
                "Access denied: enable the Google Docs API (and Google Drive API) for the OAuth client's project and grant the permissions."
            )
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Google returned {response.status_code}.")

    @staticmethod
    def _validate_per_user(credentials: Mapping[str, Any]) -> None:
        """No user to sign in as yet: check the fields users' sign-ins will depend on."""
        if not (credentials.get("client_id") or "").strip() or not (credentials.get("client_secret") or "").strip():
            raise ToolProviderCredentialValidationError("Each user signs in needs the OAuth client's Client ID and Client Secret.")
        parsed = urllib.parse.urlparse((credentials.get("redirect_uri") or "").strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the Sign-in Callback URL: create the plugin's 'Google Docs sign-in' "
                "endpoint and paste its /google_docs/callback URL."
            )
        if parsed.scheme != "https" and (parsed.hostname or "").lower() not in ("localhost", "127.0.0.1"):
            raise ToolProviderCredentialValidationError("Google only accepts https redirect URIs (or http://localhost).")
        if (parsed.hostname or "").lower() in ("localhost", "127.0.0.1", "::1"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL points to localhost, so users' browsers cannot reach it. Replace "
                "'localhost' with your Dify domain (or set ENDPOINT_URL_TEMPLATE so Dify shows the right URL)."
            )
        if not parsed.path.endswith("/google_docs/callback"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL should be the 'Google Docs sign-in' endpoint URL ending in /google_docs/callback."
            )
