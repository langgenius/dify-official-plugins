import secrets
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import (
    ToolProviderCredentialValidationError,
    ToolProviderOAuthError,
)
from werkzeug import Request

from tools.graph_client import (
    CLOUDS,
    DEFAULT_CLOUD,
    GraphAuthError,
    acquire_app_token,
    cloud_hosts,
    is_per_user,
    is_service_principal,
    resolve_graph_context,
)


class Excel365Provider(ToolProvider):
    """Microsoft Excel 365: OAuth, Service Principal, or each chat user signing in."""

    # Hardcoded SCOPE - every scope the tools rely on at runtime must be listed here,
    # and every scope listed here must also be granted on the Azure app registration:
    # a missing scope makes Microsoft Graph reject the call, while requesting a scope
    # the app registration never had consented sends the user through consent again.
    # - User.Read: least privileged permission for the `GET /me` validation call
    # - Files.ReadWrite: read/write workbooks in the signed-in user's OneDrive
    # - Files.ReadWrite.All: read/write workbooks outside the user's own OneDrive,
    #   which is what the `site_id` parameter targets
    # - Sites.Read.All: kept for SharePoint access; the drive endpoints accept it as an
    #   alternative to Files.ReadWrite.All and it has been requested since `site_id`
    #   support was added, so dropping it would be a separate, testable change
    # - offline_access: obtain a refresh token
    _SCOPES = (
        "offline_access User.Read Files.ReadWrite Files.ReadWrite.All Sites.Read.All"
    )

    # ── OAuth ──────────────────────────────────────────────────────────

    def _oauth_endpoints(self, system_credentials: Mapping[str, Any]) -> tuple[str, str, str]:
        """(authorize URL, token URL, Graph host) for the configured tenant and cloud."""
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
        """Outside the global cloud each permission is qualified with that cloud's Graph host."""
        _, _, graph_host = self._oauth_endpoints(system_credentials)
        if graph_host == CLOUDS[DEFAULT_CLOUD][1]:
            return self._SCOPES
        return " ".join(s if s == "offline_access" else f"{graph_host}/{s}" for s in self._SCOPES.split())

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
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
            raise ToolProviderOAuthError("No authorization code provided")
        _, token_url, graph_host = self._oauth_endpoints(system_credentials)
        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": self._oauth_scope(system_credentials),
        }
        response = requests.post(
            token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30
        )
        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to get access token: {response.text}")
        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise ToolProviderOAuthError(f"No access token in response: {response_json}")
        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": response_json.get("refresh_token"),
                "graph_base_url": graph_host,
            },
            expires_at=int(time.time()) + int(response_json.get("expires_in", 3600)),
        )

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available")
        _, token_url, graph_host = self._oauth_endpoints(system_credentials)

        # No `scope` here on purpose: on the refresh leg it has to be equivalent to or a
        # subset of the scopes of the original authorization request, so sending the
        # current _SCOPES would break connections that were authorized with an older,
        # narrower set. Omitting it returns a token for everything already consented.
        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        response = requests.post(
            token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30
        )
        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to refresh token: {response.text}")
        response_json = response.json()
        new_access_token = response_json.get("access_token")
        if not new_access_token:
            raise ToolProviderOAuthError(f"No access token in refresh response: {response_json}")
        return ToolOAuthCredentials(
            credentials={
                "access_token": new_access_token,
                "refresh_token": response_json.get("refresh_token", refresh_token),
                # Connections authorized before national-cloud support keep using the global cloud.
                "graph_base_url": credentials.get("graph_base_url") or graph_host,
            },
            expires_at=int(time.time()) + int(response_json.get("expires_in", 3600)),
        )

    # ── validation ─────────────────────────────────────────────────────

    def _validate_credentials(self, credentials: dict) -> None:
        if is_per_user(credentials):
            self._validate_per_user(credentials)
            return
        if is_service_principal(credentials):
            self._validate_service_principal(credentials)
            return
        self._validate_oauth(credentials)

    def _validate_oauth(self, credentials: Mapping[str, Any]) -> None:
        try:
            ctx = resolve_graph_context(credentials)
            response = requests.get(
                f"{ctx.api_base}/me",
                headers={"Authorization": f"Bearer {ctx.access_token}", "Accept": "application/json"},
                timeout=10,
            )
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Network error: {e}") from e
        if response.status_code == 401:
            raise ToolProviderCredentialValidationError("Invalid or expired access token.")
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(f"API validation failed: {response.text}")

    def _validate_service_principal(self, credentials: Mapping[str, Any]) -> None:
        """
        Sign in as the app; with a default drive owner, also open that OneDrive. Entra ID issues
        a token even without Graph permissions, so only the drive read proves Files.ReadWrite.All.
        """
        try:
            token = acquire_app_token(
                credentials.get("tenant_id", ""), credentials.get("client_id", ""),
                credentials.get("client_secret", ""), credentials.get("cloud"),
            )
            owner = (credentials.get("drive_user") or "").strip()
            if not owner:
                return  # tools name a Site ID or Drive Owner per call
            ctx = resolve_graph_context(credentials)
            response = requests.get(ctx.drive_base, headers={"Authorization": f"Bearer {token}"}, params={"$select": "id"}, timeout=30)
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Could not reach Microsoft Graph: {e}") from e
        if response.status_code == 200:
            return
        if response.status_code in (401, 403):
            raise ToolProviderCredentialValidationError(
                f"Signed in, but the app may not open the OneDrive of '{owner}'. Add the Microsoft Graph "
                "application permission Files.ReadWrite.All and grant admin consent."
            )
        if response.status_code == 404:
            raise ToolProviderCredentialValidationError(
                f"'{owner}' was not found in this tenant, or has no OneDrive yet (it is created when the user "
                "first opens OneDrive, and needs a license that includes OneDrive)."
            )
        raise ToolProviderCredentialValidationError(f"Microsoft Graph returned {response.status_code}: {response.text}")

    def _validate_per_user(self, credentials: Mapping[str, Any]) -> None:
        """
        There is no user to sign in as yet, so check what can be checked: the fields, and
        (for a single-tenant app) that the client ID and secret are accepted by Entra ID.
        """
        if not (credentials.get("client_id") or "").strip() or not (credentials.get("client_secret") or "").strip():
            raise ToolProviderCredentialValidationError("Client ID and Client Secret are required.")
        parsed = urllib.parse.urlparse((credentials.get("redirect_uri") or "").strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the Sign-in Callback URL: create the plugin's 'Excel sign-in' "
                "endpoint and paste its /excel/callback URL."
            )
        if (parsed.hostname or "").lower() in ("localhost", "127.0.0.1", "::1"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL points to localhost, so users' browsers cannot reach it. Replace "
                "'localhost' with your Dify domain (or set ENDPOINT_URL_TEMPLATE so Dify shows the right URL)."
            )
        if not parsed.path.endswith("/excel/callback"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL should be the 'Excel sign-in' endpoint URL ending in /excel/callback."
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
