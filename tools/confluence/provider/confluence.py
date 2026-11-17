import secrets
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError
from werkzeug import Request

from tools import atlassian
from tools.confluence_client import ConfluenceAuthError, confluence_request, is_per_user, resolve_context


class ConfluenceProvider(ToolProvider):
    """Confluence through an API token, an Atlassian OAuth sign-in, or each chat user signing in."""

    # ── OAuth (Atlassian 3LO) ──────────────────────────────────────────

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        if not system_credentials.get("client_id"):
            raise ToolProviderCredentialValidationError("Client ID is required for OAuth.")
        return atlassian.authorization_url(
            system_credentials["client_id"], redirect_uri, secrets.token_urlsafe(16), atlassian.scope(system_credentials)
        )

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        if request.args.get("error"):
            raise ToolProviderOAuthError(
                f"Atlassian sign-in failed: {request.args.get('error_description') or request.args['error']}"
            )
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError("Authorization code is missing in the request.")
        try:
            payload = atlassian.token_request(
                {
                    "grant_type": "authorization_code",
                    "client_id": system_credentials.get("client_id", ""),
                    "client_secret": system_credentials.get("client_secret", ""),
                    "code": code,
                    "redirect_uri": redirect_uri,
                }
            )
            site = atlassian.find_site(payload["access_token"], system_credentials.get("site_url"))
        except atlassian.AtlassianAuthError as e:
            raise ToolProviderOAuthError(str(e)) from e
        return self._credentials(payload, site, atlassian.account_name(payload["access_token"], site["cloud_id"]) or "")

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available; authorize the plugin again.")
        try:
            payload = atlassian.token_request(
                {
                    "grant_type": "refresh_token",
                    "client_id": system_credentials.get("client_id", ""),
                    "client_secret": system_credentials.get("client_secret", ""),
                    "refresh_token": refresh_token,
                }
            )
        except atlassian.AtlassianAuthError as e:
            raise ToolProviderOAuthError(str(e)) from e
        # Atlassian rotates refresh tokens: the old one stops working once the new one is used.
        payload.setdefault("refresh_token", refresh_token)
        site = {"cloud_id": credentials.get("cloud_id", ""), "site_url": credentials.get("site_url", "")}
        return self._credentials(payload, site, credentials.get("account", ""))

    @staticmethod
    def _credentials(payload: Mapping[str, Any], site: Mapping[str, str], account: str) -> ToolOAuthCredentials:
        return ToolOAuthCredentials(
            credentials={
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token", ""),
                "cloud_id": site["cloud_id"],
                "site_url": site.get("site_url", ""),
                "account": account,
            },
            expires_at=int(time.time()) + int(payload.get("expires_in", 3600)),
        )

    # ── validation ─────────────────────────────────────────────────────

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if is_per_user(credentials):
            self._validate_per_user(credentials)
            return
        try:
            ctx = resolve_context(credentials)
            if ctx.cloud:
                confluence_request(ctx, "GET", ctx.v2("spaces"), params={"limit": 1})
            else:
                confluence_request(ctx, "GET", ctx.v1("space"), params={"limit": 1})
        except ConfluenceAuthError as e:
            raise ToolProviderCredentialValidationError(f"Confluence authentication failed: {e}") from None

    @staticmethod
    def _validate_per_user(credentials: Mapping[str, Any]) -> None:
        """No user to sign in as yet: check the fields users' sign-ins will depend on."""
        if not (credentials.get("client_id") or "").strip() or not (credentials.get("client_secret") or "").strip():
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the Client ID and Client Secret of an Atlassian OAuth 2.0 (3LO) app."
            )
        parsed = urllib.parse.urlparse((credentials.get("redirect_uri") or "").strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the Sign-in Callback URL: create the plugin's 'Confluence sign-in' "
                "endpoint and paste its /confluence/callback URL."
            )
        if (parsed.hostname or "").lower() in ("localhost", "127.0.0.1", "::1"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL points to localhost, so users' browsers cannot reach it. Replace "
                "'localhost' with your Dify domain (or set ENDPOINT_URL_TEMPLATE so Dify shows the right URL)."
            )
        if not parsed.path.endswith("/confluence/callback"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL should be the 'Confluence sign-in' endpoint URL ending in /confluence/callback."
            )
