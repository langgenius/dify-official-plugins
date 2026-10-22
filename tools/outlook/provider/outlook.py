import time
from typing import Any, Mapping
import requests
import secrets
import urllib.parse

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.oauth import ToolOAuthCredentials

from tools.graph_client import (
    GraphAuthError,
    cloud_hosts,
    is_service_principal,
    resolve_graph_context,
)


class OutlookProvider(ToolProvider):
    # Calendars.Read.Shared: calendars other people shared with the user (e.g. an executive's, for an assistant).
    _SCOPE = "Mail.Read Mail.Send Mail.ReadWrite Calendars.ReadWrite Calendars.Read.Shared offline_access"

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate credentials by calling Microsoft Graph API."""
        if is_service_principal(credentials):
            self._validate_service_principal(credentials)
            return

        if not credentials.get("access_token"):
            raise ToolProviderCredentialValidationError("Microsoft Graph access token is required.")

        try:
            ctx = resolve_graph_context(credentials)
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        headers = {"Authorization": f"Bearer {ctx.access_token}"}
        response = requests.get(ctx.mailbox_base, headers=headers, timeout=30)

        if response.status_code != 200:
            raise ToolProviderCredentialValidationError("Invalid or expired access token.")

    def _validate_service_principal(self, credentials: Mapping[str, Any]) -> None:
        """
        Sign in as the app, then read the default mailbox's inbox.

        Entra ID issues a token even when the app has no Graph permissions at all, so a
        successful sign-in alone proves nothing; the mailbox read is what shows that the
        application permissions are granted and admin-consented.
        """
        try:
            ctx = resolve_graph_context(credentials)
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e

        try:
            response = requests.get(
                f"{ctx.mailbox_base}/mailFolders/inbox",
                headers={"Authorization": f"Bearer {ctx.access_token}"},
                params={"$select": "id"},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Could not reach Microsoft Graph: {e}") from e

        if response.status_code == 200:
            return
        mailbox = credentials.get("mailbox")
        if response.status_code in (401, 403):
            raise ToolProviderCredentialValidationError(
                f"Signed in, but the app may not read the mailbox '{mailbox}'. Add the Microsoft Graph "
                "application permissions (Mail.ReadWrite, Mail.Send, Calendars.ReadWrite), grant admin "
                "consent, and check that no Exchange application access policy excludes this mailbox."
            )
        if response.status_code == 404:
            raise ToolProviderCredentialValidationError(
                f"Mailbox '{mailbox}' was not found in this tenant, or it has no Exchange Online mailbox."
            )
        raise ToolProviderCredentialValidationError(
            f"Microsoft Graph returned {response.status_code}: {response.text}"
        )

    def _oauth_scope(self, system_credentials: Mapping[str, Any]) -> str:
        """
        Delegated scopes for the sign-in. Outside the global cloud each permission is
        qualified with that cloud's Graph host, otherwise Entra resolves the short names
        against graph.microsoft.com.
        """
        scope = system_credentials.get("scope", self._SCOPE)
        _, _, graph_host = self._oauth_endpoints(system_credentials)
        if graph_host == cloud_hosts("global")[1]:
            return scope
        qualified = []
        for item in scope.split():
            if item in ("offline_access", "openid", "profile", "email") or "://" in item:
                qualified.append(item)
            else:
                qualified.append(f"{graph_host}/{item}")
        return " ".join(qualified)

    def _oauth_endpoints(self, system_credentials: Mapping[str, Any]) -> tuple[str, str, str]:
        """Return (authorize URL, token URL, Graph host) for the configured tenant and cloud."""
        try:
            login_host, graph_host = cloud_hosts(system_credentials.get("cloud"))
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        tenant_id = system_credentials.get("tenant_id") or "common"
        base = f"{login_host}/{tenant_id}/oauth2/v2.0"
        return f"{base}/authorize", f"{base}/token", graph_host

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """Generate OAuth authorization URL."""
        auth_url, _, _ = self._oauth_endpoints(system_credentials)

        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": self._oauth_scope(system_credentials),
            "response_type": "code",
            "state": secrets.token_urlsafe(16)
        }
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Any
    ) -> ToolOAuthCredentials:
        """Exchange authorization code for access token."""
        # Get authorization code
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError("No authorization code provided")

        # Exchange code for token
        _, token_url, graph_host = self._oauth_endpoints(system_credentials)

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }

        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Token exchange failed: {response.text}")

        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token or not refresh_token:
            raise ToolProviderCredentialValidationError("No access token or refresh token in response")

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "graph_base_url": graph_host,
            },
            expires_at= token_data.get("expires_in", 3599) + int(time.time())
        )

    def oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:

        """Refresh OAuth credentials."""
        _, token_url, graph_host = self._oauth_endpoints(system_credentials)

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": credentials.get("refresh_token"),
            "redirect_uri": redirect_uri,
            "grant_type": "refresh_token"
        }

        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Token exchange failed: {response.text}")

        token_data = response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token or not refresh_token:
            raise ToolProviderCredentialValidationError("No access token or refresh token in response")

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "graph_base_url": graph_host,
            },
            expires_at= token_data.get("expires_in", 3599) + int(time.time())
        )
