import urllib
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request

from dify_plugin.entities.datasource import DatasourceOAuthCredentials
from dify_plugin.errors.tool import DatasourceOAuthError, ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider

__TIMEOUT_SECONDS__ = 60 * 10


class NotionDatasourceProvider(DatasourceProvider):
    API_VERSION = "2022-06-28"  # Using a stable API version
    _AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
    _TOKEN_URL = "https://api.notion.com/v1/oauth/token"

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate the authorization URL for the Notion OAuth.
        """
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "owner": "user",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """
        Get the credentials for the Notion OAuth.
        """
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("No code provided")

        data = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json"}
        auth = (system_credentials["client_id"], system_credentials["client_secret"])
        response = requests.post(self._TOKEN_URL, data=data, auth=auth, headers=headers, timeout=__TIMEOUT_SECONDS__)
        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise DatasourceOAuthError(f"Error in Notion OAuth: {response_json}")

        workspace_name = response_json.get("workspace_name")
        workspace_icon = response_json.get("workspace_icon")
        workspace_id = response_json.get("workspace_id")

        return DatasourceOAuthCredentials(
            name=workspace_name,
            avatar_url=workspace_icon,
            credentials={
                "integration_secret": access_token,
                "workspace_name": workspace_name,
                "workspace_icon": workspace_icon,
                "workspace_id": workspace_id,
            },
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        """
        Refresh the credentials for the Notion OAuth.

        Note: Notion OAuth API does not support refresh tokens.
        When the access token expires, users need to re-authorize through the OAuth flow.
        """
        pass

    def _validate_credentials(self, credentials: Mapping[str, Any]):
        try:
            # Check if integration_token is provided
            if "integration_secret" not in credentials or not credentials.get("integration_secret"):
                raise ToolProviderCredentialValidationError("Notion Integration Token is required.")

            # Try to authenticate with Notion API by making a test request
            integration_secret = credentials.get("integration_secret")

            try:
                # Initialize the Notion client and attempt to fetch the current user
                headers = {
                    "Authorization": f"Bearer {integration_secret}",
                    "Notion-Version": self.API_VERSION,
                    "Content-Type": "application/json",
                }
                # Make a request to the users endpoint to validate the token
                response = requests.get(
                    "https://api.notion.com/v1/users/me", headers=headers, timeout=__TIMEOUT_SECONDS__
                )
                if response.status_code == 401:
                    raise ToolProviderCredentialValidationError("Invalid Notion Integration Token.")
                elif response.status_code != 200:
                    raise ToolProviderCredentialValidationError(
                        f"Failed to connect to Notion API: {response.status_code} {response.text}"
                    )
                else:
                    return True
            except requests.RequestException as e:
                raise ToolProviderCredentialValidationError(
                    f"Network error when connecting to Notion API: {e!s}"
                ) from e

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
