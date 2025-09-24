import urllib.parse
import time
from collections.abc import Mapping
from typing import Any

import requests
from dify_plugin.entities.datasource import DatasourceOAuthCredentials
from dify_plugin.errors.tool import (
    DatasourceOAuthError,
    ToolProviderCredentialValidationError,
)
from dify_plugin.interfaces.datasource import DatasourceProvider
from werkzeug import Request

__TIMEOUT_SECONDS__ = 60 * 60


class ConfluenceDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://auth.atlassian.com/authorize"
    _TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    _RESOURCE_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
    _API_BASE = "https://api.atlassian.com/ex/confluence"

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        params = {
            "audience": "api.atlassian.com",
            "client_id": system_credentials["client_id"],
            "scope": "offline_access read:confluence-content.all read:confluence-space.summary read:confluence-props read:confluence-user read:page:confluence",
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
        response = requests.post(self._TOKEN_URL, data=data, timeout=__TIMEOUT_SECONDS__)
        if response.status_code != 200:
            raise DatasourceOAuthError(f"Token request failed: {response.status_code} {response.text}")
        
        response_json = response.json()
        access_token = response_json.get("access_token")
        refresh_token = response_json.get("refresh_token")
        expires_in = response_json.get("expires_in")
        if not access_token:
            raise DatasourceOAuthError(f"OAuth failed: {response_json}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        res = requests.get(self._RESOURCE_URL, headers=headers, timeout=10)
        if res.status_code != 200:
            raise DatasourceOAuthError(f"Failed to get resources: {res.status_code} {res.text}")
        
        resources = res.json()
        if not resources or len(resources) == 0:
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
                "refresh_token": refresh_token,
                "workspace_id": cloud_id,
                "workspace_name": workspace_name,
                "workspace_icon": workspace_url,
            },
            expires_at=int(time.time()) + expires_in if expires_in else -1,
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ):
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("No refresh token available. Please reauthorize.")
        
        data = {
            "grant_type": "refresh_token",
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
        }
        
        response = requests.post(self._TOKEN_URL, data=data, timeout=__TIMEOUT_SECONDS__)
        if response.status_code != 200:
            raise DatasourceOAuthError(f"Token refresh failed: {response.status_code} {response.text}")
        
        response_json = response.json()
        new_access_token = response_json.get("access_token")
        new_refresh_token = response_json.get("refresh_token", refresh_token)  # Some providers return new refresh token
        
        if not new_access_token:
            raise DatasourceOAuthError(f"Token refresh failed: {response_json}")
        
        # Keep existing workspace info
        return DatasourceOAuthCredentials(
            name=credentials.get("workspace_name", "Confluence"),
            avatar_url=credentials.get("workspace_icon"),
            credentials={
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "workspace_id": credentials.get("workspace_id"),
                "workspace_name": credentials.get("workspace_name"),
                "workspace_icon": credentials.get("workspace_icon"),
            },
        )

    def _validate_credentials(self, credentials: Mapping[str, Any]):
        pass