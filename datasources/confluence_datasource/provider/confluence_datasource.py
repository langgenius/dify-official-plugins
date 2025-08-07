import base64
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request

from dify_plugin.entities.datasource import DatasourceOAuthCredentials
from dify_plugin.errors.tool import DatasourceOAuthError, ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider

__TIMEOUT_SECONDS__ = 60 * 10


class ConfluenceDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://auth.atlassian.com/authorize"
    _TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    _RESOURCE_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
    _API_BASE = "https://api.atlassian.com/ex/confluence"

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        params = {
            "audience": "api.atlassian.com",
            "client_id": system_credentials["client_id"],
            "scope": "read:confluence-content.all read:confluence-space.summary read:confluence-user.account.readonly",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "prompt": "consent",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("No code provided")

        data = {
            "grant_type": "authorization_code",
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
        }
        response = requests.post(self._TOKEN_URL, json=data, timeout=__TIMEOUT_SECONDS__)
        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise DatasourceOAuthError(f"OAuth failed: {response_json}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        res = requests.get(self._RESOURCE_URL, headers=headers, timeout=10)
        resources = res.json()
        if not resources:
            raise DatasourceOAuthError("No Confluence workspace found for this account.")

        resource = resources[0]
        cloud_id = resource["id"]
        workspace_name = resource["name"]
        workspace_url = resource.get("url")

        return DatasourceOAuthCredentials(
            name=workspace_name,
            avatar_url=workspace_url,
            credentials={
                "access_token": access_token,
                "workspace_id": cloud_id,
                "workspace_name": workspace_name,
                "workspace_icon": workspace_url,
            },
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ):
        raise DatasourceOAuthError("Confluence does not support token refreshing in this plugin. Please reauthorize.")

    def _validate_credentials(self, credentials: Mapping[str, Any]):
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ToolProviderCredentialValidationError("API key missing")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
            test_url = f"{self._API_BASE}/wiki/api/v2/spaces"
            res = requests.get(test_url, headers=headers, timeout=10)
            if res.status_code != 200:
                raise ToolProviderCredentialValidationError(f"Validation failed: {res.status_code} {res.text}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e