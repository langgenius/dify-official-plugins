import time
from typing import Any, Mapping

import requests
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from msal import ConfidentialClientApplication
from werkzeug import Request

from tools.graph_client import GraphAuthError, cloud_hosts, is_service_principal, resolve_graph_context


class OneDriveProvider(ToolProvider):

    _scope = [
        "Files.Read.All",
        "Files.ReadWrite.All",
    ]

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Only Service Principal credentials reach this; OAuth goes through the sign-in.

        Sign in as the app, then open the default drive owner's OneDrive. Entra ID issues
        a token even when the app has no Graph permissions, so the sign-in alone proves
        nothing; reading the drive shows that Files.ReadWrite.All is granted and consented.
        """
        if not is_service_principal(credentials):
            return
        try:
            ctx = resolve_graph_context(credentials)
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        try:
            response = requests.get(
                ctx.drive_base,
                headers={"Authorization": f"Bearer {ctx.access_token}"},
                params={"$select": "id"},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Could not reach Microsoft Graph: {e}") from e

        if response.status_code == 200:
            return
        owner = credentials.get("drive_user")
        if response.status_code in (401, 403):
            raise ToolProviderCredentialValidationError(
                f"Signed in, but the app may not open the OneDrive of '{owner}'. Add the Microsoft Graph "
                "application permission Files.ReadWrite.All and grant admin consent."
            )
        if response.status_code == 404:
            raise ToolProviderCredentialValidationError(
                f"'{owner}' was not found in this tenant, or has no OneDrive yet (it is created when the "
                "user first opens OneDrive, and needs a license that includes OneDrive)."
            )
        raise ToolProviderCredentialValidationError(
            f"Microsoft Graph returned {response.status_code}: {response.text}"
        )

    def _app(self, system_credentials: Mapping[str, Any]) -> tuple[ConfidentialClientApplication, list[str]]:
        """MSAL app for the configured tenant and cloud, and the scopes to request there."""
        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise ToolProviderCredentialValidationError(
                "Client ID and Client Secret are required for OAuth."
            )
        try:
            login_host, graph_host = cloud_hosts(system_credentials.get("cloud"))
        except GraphAuthError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        # "common" keeps the old behaviour (any work/school or personal account) when no tenant is set.
        tenant_id = (system_credentials.get("tenant_id") or "common").strip()
        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"{login_host}/{tenant_id}",
        )
        if graph_host == cloud_hosts("global")[1]:
            return app, list(self._scope)
        # Outside the global cloud, qualify the permissions with that cloud's Graph host.
        return app, [f"{graph_host}/{scope}" for scope in self._scope]

    def _credentials_from(self, token_dict: Mapping[str, Any], system_credentials: Mapping[str, Any]) -> ToolOAuthCredentials:
        if "access_token" not in token_dict:
            detail = token_dict.get("error_description") or token_dict.get("error") or "no access token returned"
            raise ToolProviderCredentialValidationError(f"Microsoft sign-in failed: {detail}")
        _, graph_host = cloud_hosts(system_credentials.get("cloud"))
        expires_at = int(token_dict.get("expires_in", 3599)) + int(time.time())
        return ToolOAuthCredentials(
            credentials={
                "access_token": token_dict["access_token"],
                "refresh_token": token_dict.get("refresh_token"),
                "expire_at": expires_at,
                "graph_base_url": graph_host,
            },
            expires_at=expires_at,
        )

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        app, scopes = self._app(system_credentials)
        return app.get_authorization_request_url(
            redirect_uri=redirect_uri, scopes=scopes, response_type="code"
        )

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError(
                "Authorization code is missing in the request."
            )
        app, scopes = self._app(system_credentials)
        token_dict = app.acquire_token_by_authorization_code(code, scopes, redirect_uri)
        return self._credentials_from(token_dict, system_credentials)

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        app, scopes = self._app(system_credentials)
        token_dict = app.acquire_token_by_refresh_token(credentials["refresh_token"], scopes)
        result = self._credentials_from(token_dict, system_credentials)
        if not result.credentials.get("refresh_token"):
            # Entra may omit a new refresh token; keep using the current one.
            result.credentials["refresh_token"] = credentials["refresh_token"]
        return result
