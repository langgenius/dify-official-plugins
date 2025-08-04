import time
from typing import Any, Mapping

from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from msal import ConfidentialClientApplication
from werkzeug import Request


class OneDriveProvider(ToolProvider):

    _authority = "https://login.microsoftonline.com/common"
    _scope = [
        "Files.Read.All",
        "Files.ReadWrite.All",
    ]

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        # logger.debug(f"Redirect URI: {redirect_uri}")
        # logger.debug(f"System Credentials: {system_credentials}")

        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise ToolProviderCredentialValidationError(
                "Client ID and Client Secret are required for OAuth."
            )

        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=self._authority,
        )

        return app.get_authorization_request_url(
            redirect_uri=redirect_uri, scopes=self._scope, response_type="code"
        )

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        # log.debug(f"Redirect URI: {redirect_uri}")
        # log.debug(f"System Credentials: {system_credentials}")

        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError(
                "Authorization code is missing in the request."
            )

        app = ConfidentialClientApplication(
            client_id=system_credentials["client_id"],
            client_credential=system_credentials["client_secret"],
            authority=self._authority,
        )
        token_dict = app.acquire_token_by_authorization_code(
            code, self._scope, redirect_uri
        )

        access_token = token_dict["access_token"]
        expires_at = token_dict["expires_in"] + int(time.time())
        refresh_token = token_dict["refresh_token"]

        # logger.debug(
        #     f"Access Token: {access_token}, Expires At: {expires_at}, Refresh Token: {refresh_token}"
        # )

        credentials = ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expire_at": expires_at,
            },
            expires_at=expires_at,
        )
        return credentials

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        app = ConfidentialClientApplication(
            client_id=system_credentials["client_id"],
            client_credential=system_credentials["client_secret"],
            authority=self._authority,
        )
        token_dict = app.acquire_token_by_refresh_token(
            credentials["refresh_token"], self._scope
        )
        access_token = token_dict["access_token"]
        expires_at = token_dict["expires_in"] + int(time.time())
        refresh_token = token_dict["refresh_token"]

        # logger.debug(
        #     f"Access Token: {access_token}, Expires At: {expires_at}, Refresh Token: {refresh_token}"
        # )

        credentials = ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expire_at": expires_at,
            },
            expires_at=expires_at,
        )
        return credentials
