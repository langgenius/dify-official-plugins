import urllib
from typing import Any, Mapping

import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider
from werkzeug import Request


class NotionDatasourceProvider(DatasourceProvider):
    API_VERSION = "2022-06-28"  # Using a stable API version
    _AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
    _TOKEN_URL = "https://api.notion.com/v1/oauth/token"

    def _oauth_get_authorization_url(
        self, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for the Notion OAuth.
        """
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": system_credentials["redirect_uri"],
            "owner": "user",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, system_credentials: Mapping[str, Any], request: Request
    ) -> Mapping[str, Any]:
        """
        Get the credentials for the Notion OAuth.
        """
        code = request.args.get("code")
        if not code:
            raise ValueError("No code provided")

        data = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": system_credentials["redirect_uri"],
        }
        headers = {"Accept": "application/json"}
        auth = (system_credentials["client_id"], system_credentials["client_secret"])
        response = requests.post(
            self._TOKEN_URL, data=data, auth=auth, headers=headers, timeout=10
        )
        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise ValueError(f"Error in Notion OAuth: {response_json}")

        workspace_name = response_json.get("workspace_name")
        workspace_icon = response_json.get("workspace_icon")
        workspace_id = response_json.get("workspace_id")

        return {
            "access_token": access_token,
            "workspace_name": workspace_name,
            "workspace_icon": workspace_icon,
            "workspace_id": workspace_id,
        }

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            # Check if integration_token is provided
            if "integration_secret" not in credentials or not credentials.get(
                "integration_secret"
            ):
                raise ToolProviderCredentialValidationError(
                    "Notion Integration Token is required."
                )

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
                    "https://api.notion.com/v1/users/me", headers=headers
                )
                if response.status_code == 401:
                    raise ToolProviderCredentialValidationError(
                        "Invalid Notion Integration Token."
                    )
                elif response.status_code != 200:
                    raise ToolProviderCredentialValidationError(
                        f"Failed to connect to Notion API: {response.status_code} {response.text}"
                    )
                else:
                    return True
            except requests.RequestException as e:
                raise ToolProviderCredentialValidationError(
                    f"Network error when connecting to Notion API: {str(e)}"
                )

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
