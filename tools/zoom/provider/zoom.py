import base64
import json
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


class ZoomProvider(ToolProvider):
    _AUTH_URL = "https://zoom.us/oauth/authorize"
    _TOKEN_URL = "https://zoom.us/oauth/token"
    _API_USER_URL = "https://api.zoom.us/v2/users/me"

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for the Zoom OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "response_type": "code",
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange code for access_token.
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No authorization code provided")

        # Optionally validate state for security
        state = request.args.get("state")
        if not state:
            raise ToolProviderOAuthError("No state parameter provided")

        # Prepare credentials for Basic Auth
        credentials = (
            f"{system_credentials['client_id']}:{system_credentials['client_secret']}"
        )
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=10
        )

        if response.status_code != 200:
            error_data = (
                response.json()
                if response.headers.get("content-type") == "application/json"
                else {}
            )
            error_msg = error_data.get(
                "error_description", f"Token exchange failed: {response.text}"
            )
            raise ToolProviderOAuthError(f"Error in Zoom OAuth: {error_msg}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        refresh_token = response_json.get("refresh_token")
        expires_in = response_json.get("expires_in", 3600)

        if not access_token:
            raise ToolProviderOAuthError(f"No access token received: {response_json}")

        # Calculate expiration time (current time + expires_in seconds)
        import time

        expires_at = (
            int(time.time()) + expires_in - 60
        )  # Subtract 60 seconds for buffer

        return ToolOAuthCredentials(
            credentials={"access_token": access_token, "refresh_token": refresh_token},
            expires_at=expires_at,
        )

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        """
        Refresh the access token using refresh token
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available")

        # Prepare credentials for Basic Auth
        auth_credentials = (
            f"{system_credentials['client_id']}:{system_credentials['client_secret']}"
        )
        encoded_credentials = base64.b64encode(auth_credentials.encode()).decode()

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=10
        )

        if response.status_code != 200:
            error_data = (
                response.json()
                if response.headers.get("content-type") == "application/json"
                else {}
            )
            error_msg = error_data.get(
                "error_description", f"Token refresh failed: {response.text}"
            )
            raise ToolProviderOAuthError(f"Error refreshing Zoom token: {error_msg}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        new_refresh_token = response_json.get(
            "refresh_token", refresh_token
        )  # Use old refresh token if new one not provided
        expires_in = response_json.get("expires_in", 3600)

        if not access_token:
            raise ToolProviderOAuthError(
                f"No access token received during refresh: {response_json}"
            )

        # Calculate expiration time
        import time

        expires_at = (
            int(time.time()) + expires_in - 60
        )  # Subtract 60 seconds for buffer

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": new_refresh_token,
            },
            expires_at=expires_at,
        )

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate Zoom OAuth credentials
        """
        try:
            access_token = credentials.get("access_token")

            if not access_token:
                raise ToolProviderCredentialValidationError(
                    "Zoom Access Token is required."
                )

            # Test the credentials by making a simple API call
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Test with a simple user info request
            response = requests.get(self._API_USER_URL, headers=headers, timeout=10)

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Invalid or expired Zoom access token."
                )
            elif response.status_code != 200:
                error_data = (
                    response.json()
                    if response.headers.get("content-type") == "application/json"
                    else {}
                )
                error_msg = error_data.get("message", response.text)
                raise ToolProviderCredentialValidationError(
                    f"Failed to validate Zoom credentials: {error_msg}"
                )

        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Network error occurred: {str(e)}"
            ) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Validation error: {str(e)}"
            ) from e
