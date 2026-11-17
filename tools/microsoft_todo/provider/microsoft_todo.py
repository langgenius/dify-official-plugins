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

from tools.graph_client import (
    CLOUDS,
    DEFAULT_CLOUD,
    GraphAuthError,
    acquire_app_token,
    cloud_hosts,
    is_per_user,
    is_service_principal,
    legacy_token,
    resolve_graph_context,
)


class MicrosoftTodoProvider(ToolProvider):
    """Microsoft To Do: OAuth, Service Principal, or each chat user signing in."""

    # The scopes requested since the first version (they were pymstodo's), so existing
    # authorizations and app registrations keep matching.
    _SCOPE = "openid offline_access Tasks.ReadWrite"

    # ── OAuth ──────────────────────────────────────────────────────────

    def _oauth_endpoints(self, system_credentials: Mapping[str, Any]) -> tuple[str, str, str]:
        """(authorize URL, token URL, Graph host) for the configured tenant and cloud."""
        client_id = system_credentials.get("client_id")
        if not client_id:
            raise ToolProviderCredentialValidationError("Client ID is required for OAuth.")
        try:
            login_host, graph_host = cloud_hosts(system_credentials.get("cloud"))
        except GraphAuthError as e:
            raise ToolProviderOAuthError(str(e)) from e
        # "common" keeps the behaviour from before the setting existed.
        tenant_id = (system_credentials.get("tenant_id") or "common").strip()
        if any(c in tenant_id for c in "/?# "):
            raise ToolProviderOAuthError("Tenant ID must be a GUID, a domain name, or common / organizations.")
        base = f"{login_host}/{tenant_id}/oauth2/v2.0"
        return f"{base}/authorize", f"{base}/token", graph_host

    def _oauth_scope(self, system_credentials: Mapping[str, Any]) -> str:
        """Outside the global cloud each Graph permission is qualified with that cloud's Graph host."""
        _, _, graph_host = self._oauth_endpoints(system_credentials)
        if graph_host == CLOUDS[DEFAULT_CLOUD][1]:
            return self._SCOPE
        return " ".join(s if s in ("openid", "offline_access") else f"{graph_host}/{s}" for s in self._SCOPE.split())

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        auth_url, _, _ = self._oauth_endpoints(system_credentials)
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": self._oauth_scope(system_credentials),
            "state": secrets.token_urlsafe(16),
        }
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError("Authorization code is missing in the request.")
        _, token_url, graph_host = self._oauth_endpoints(system_credentials)
        payload = self._token_request(token_url, {
            "grant_type": "authorization_code",
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials.get("client_secret", ""),
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": self._oauth_scope(system_credentials),
        })
        return self._credentials(payload, graph_host)

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        # Authorizations from before 1.0.0 keep the token as JSON text under "token".
        refresh_token = credentials.get("refresh_token") or legacy_token(credentials).get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available; authorize the plugin again.")
        _, token_url, graph_host = self._oauth_endpoints(system_credentials)
        # No scope on the refresh: Entra returns a token for everything already consented.
        payload = self._token_request(token_url, {
            "grant_type": "refresh_token",
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials.get("client_secret", ""),
            "refresh_token": refresh_token,
        })
        payload.setdefault("refresh_token", refresh_token)
        # Authorizations made before national-cloud support keep using the global cloud.
        return self._credentials(payload, credentials.get("graph_base_url") or graph_host)

    @staticmethod
    def _token_request(token_url: str, data: Mapping[str, str]) -> dict[str, Any]:
        try:
            response = requests.post(token_url, data=data, timeout=30)
        except requests.exceptions.RequestException as e:
            raise ToolProviderOAuthError(f"Could not reach Microsoft Entra ID: {e}") from e
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200 or not payload.get("access_token"):
            detail = payload.get("error_description") or payload.get("error") or response.text[:300]
            raise ToolProviderOAuthError(f"Microsoft sign-in failed ({response.status_code}): {detail}")
        return payload

    @staticmethod
    def _credentials(payload: Mapping[str, Any], graph_host: str) -> ToolOAuthCredentials:
        return ToolOAuthCredentials(
            credentials={
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token", ""),
                "graph_base_url": graph_host,
            },
            expires_at=int(time.time()) + int(payload.get("expires_in", 3599)),
        )

    # ── validation ─────────────────────────────────────────────────────

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if is_per_user(credentials):
            self._validate_per_user(credentials)
            return
        if is_service_principal(credentials):
            self._validate_service_principal(credentials)
            return
        # OAuth: read the task lists (the OAuth scopes have no User.Read for /me).
        try:
            ctx = resolve_graph_context(credentials)
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        self._check_todo(ctx.todo_base, ctx.access_token, "the signed-in user")

    @staticmethod
    def _check_todo(todo_base: str, token: str, who: str) -> None:
        try:
            response = requests.get(
                f"{todo_base}/lists", headers={"Authorization": f"Bearer {token}"}, params={"$top": 1}, timeout=30
            )
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Could not reach Microsoft Graph: {e}") from e
        if response.status_code == 200:
            return
        if response.status_code == 401:
            raise ToolProviderCredentialValidationError("The access token is invalid or expired; authorize the plugin again.")
        if response.status_code == 403:
            raise ToolProviderCredentialValidationError(
                f"Signed in, but may not read the tasks of {who}: check the Tasks permission and its admin consent."
            )
        if response.status_code == 404:
            raise ToolProviderCredentialValidationError(
                f"No To Do data for {who}: check the user, and that they have an Exchange Online mailbox (To Do is stored there)."
            )
        raise ToolProviderCredentialValidationError(f"Microsoft Graph returned {response.status_code}.")

    def _validate_service_principal(self, credentials: Mapping[str, Any]) -> None:
        """Sign in as the app; with a default task owner, also read that user's lists (proves Tasks.ReadWrite.All)."""
        try:
            acquire_app_token(
                credentials.get("tenant_id", ""), credentials.get("client_id", ""),
                credentials.get("client_secret", ""), credentials.get("cloud"),
            )
            owner = (credentials.get("task_user") or "").strip()
            if not owner:
                return  # each tool call names the task owner
            ctx = resolve_graph_context(credentials)
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        self._check_todo(ctx.todo_base, ctx.access_token, f"'{owner}'")

    def _validate_per_user(self, credentials: Mapping[str, Any]) -> None:
        """No user to sign in as yet: check the fields and, for a single-tenant app, that Entra accepts the client ID and secret."""
        if not (credentials.get("client_id") or "").strip() or not (credentials.get("client_secret") or "").strip():
            raise ToolProviderCredentialValidationError("Client ID and Client Secret are required.")
        parsed = urllib.parse.urlparse((credentials.get("redirect_uri") or "").strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the Sign-in Callback URL: create the plugin's 'To Do sign-in' endpoint "
                "and paste its /todo/callback URL."
            )
        if (parsed.hostname or "").lower() in ("localhost", "127.0.0.1", "::1"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL points to localhost, so users' browsers cannot reach it. Replace "
                "'localhost' with your Dify domain (or set ENDPOINT_URL_TEMPLATE so Dify shows the right URL)."
            )
        if not parsed.path.endswith("/todo/callback"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL should be the 'To Do sign-in' endpoint URL ending in /todo/callback."
            )
        try:
            cloud_hosts(credentials.get("cloud"))
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        tenant_id = (credentials.get("tenant_id") or "").strip()
        if tenant_id.lower() in ("", "common", "organizations", "consumers"):
            return
        try:
            acquire_app_token(tenant_id, credentials["client_id"], credentials["client_secret"], credentials.get("cloud"))
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e).replace("Service Principal sign-in", "App sign-in")) from e
