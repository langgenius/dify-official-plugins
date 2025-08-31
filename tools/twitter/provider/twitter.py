import secrets
import time
import urllib.parse
from typing import Any, Mapping

import httpx
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from werkzeug import Request


class DifyPluginPdmTemplateProvider(ToolProvider):
    _SCOPE = "tweet.read tweet.write users.read offline.access like.read like.write"  # Scopes for basic Twitter API access
    _AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
    _TOKEN_URL = "https://api.twitter.com/2/oauth2/token"


    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        params = {
            "client_id": system_credentials.get("client_id"),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._SCOPE,
            "state": secrets.token_urlsafe(16),
            "code_challenge": "challenge",  # Placeholder for PKCE
            "code_challenge_method": "plain",  # Placeholder for PKCE
        }

        return f"{self._AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError(
                "No authorization code provided"
            )

        data = {
            "client_id": system_credentials.get("client_id"),
            "client_secret": system_credentials.get("client_secret"),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": "challenge",  # Placeholder for PKCE
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(self._TOKEN_URL, data=data)
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    "Failed to obtain access token"
                )

            token_data: dict[str, Any] = response.json()
            return ToolOAuthCredentials(
                credentials={
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                },
                expires_in=(
                    token_data.get("expires_in") + time.time()
                    if "expires_in" in token_data
                    else -1
                ),
            )

    def oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        data = {
            "client_id": system_credentials.get("client_id"),
            "client_secret": system_credentials.get("client_secret"),
            "refresh_token": credentials.get("refresh_token"),
            "grant_type": "refresh_token",
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(self._TOKEN_URL, data=data)
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    "Failed to refresh access token"
                )

            token_data: dict[str, Any] = response.json()
            return ToolOAuthCredentials(
                credentials={
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                },
                expires_in=(
                    token_data.get("expires_in") + time.time()
                    if "expires_in" in token_data
                    else -1
                ),
            )