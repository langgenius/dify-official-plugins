import secrets
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


class Excel365Provider(ToolProvider):
    """Microsoft Excel 365 provider with OAuth authentication"""

    _AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    _TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _API_BASE_URL = "https://graph.microsoft.com/v1.0"
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

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for Microsoft OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": self._SCOPES,  # Use hardcoded SCOPE
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange authorization code for access token.
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No authorization code provided")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": self._SCOPES,  # Use hardcoded SCOPE
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=30
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to get access token: {response.text}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        refresh_token = response_json.get("refresh_token")
        expires_in = response_json.get("expires_in", 3600)

        if not access_token:
            raise ToolProviderOAuthError(
                f"No access token in response: {response_json}"
            )

        # Calculate expiration time
        import time

        expires_at = int(time.time()) + expires_in

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
            expires_at=expires_at,
        )

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        """
        Refresh the access token using refresh token.
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available")

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

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=30
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to refresh token: {response.text}")

        response_json = response.json()
        new_access_token = response_json.get("access_token")
        new_refresh_token = response_json.get("refresh_token", refresh_token)
        expires_in = response_json.get("expires_in", 3600)

        if not new_access_token:
            raise ToolProviderOAuthError(
                f"No access token in refresh response: {response_json}"
            )

        # Calculate expiration time
        import time

        expires_at = int(time.time()) + expires_in

        return ToolOAuthCredentials(
            credentials={
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
            },
            expires_at=expires_at,
        )

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate the OAuth credentials by making a test API call.
        """
        try:
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("Access token is required.")

            headers = {
                "Authorization": f"Bearer {credentials['access_token']}",
                "Accept": "application/json",
            }

            # Test API call - get user information
            response = requests.get(
                f"{self._API_BASE_URL}/me", headers=headers, timeout=10
            )

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Invalid or expired access token."
                )
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"API validation failed: {response.text}"
                )

        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Network error: {str(e)}"
            ) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
