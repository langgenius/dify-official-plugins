import base64
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


class SnowflakeSQLProvider(ToolProvider):
    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for Snowflake OAuth.
        """
        account_name = system_credentials["account_name"]
        client_id = system_credentials["client_id"]

        state = secrets.token_urlsafe(16)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }

        # Add scope if provided
        scope = system_credentials.get("scope")
        if scope:
            params["scope"] = scope

        auth_url = f"https://{account_name}.snowflakecomputing.com/oauth/authorize"
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange authorization code for access token using Snowflake OAuth.
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No authorization code provided")

        account_name = system_credentials["account_name"]
        client_id = system_credentials["client_id"]
        client_secret = system_credentials["client_secret"]

        # Snowflake token endpoint
        token_url = f"https://{account_name}.snowflakecomputing.com/oauth/token-request"

        # Create Basic Auth header
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        response = requests.post(
            token_url, headers=headers, data=urllib.parse.urlencode(data), timeout=10
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Token exchange failed: {response.text}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise ToolProviderOAuthError(f"Error in Snowflake OAuth: {response_json}")

        # Calculate expiration time if expires_in is provided
        expires_at = -1
        if "expires_in" in response_json:
            import time

            expires_at = int(time.time()) + int(response_json["expires_in"])

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": response_json.get("refresh_token"),
                "account_name": account_name,
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
        Refresh Snowflake OAuth access token using refresh token.
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available")

        account_name = (
            credentials.get("account_name") or system_credentials["account_name"]
        )
        client_id = system_credentials["client_id"]
        client_secret = system_credentials["client_secret"]

        # Snowflake token endpoint
        token_url = f"https://{account_name}.snowflakecomputing.com/oauth/token-request"

        # Create Basic Auth header
        auth_credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(auth_credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        response = requests.post(
            token_url, headers=headers, data=urllib.parse.urlencode(data), timeout=10
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Token refresh failed: {response.text}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise ToolProviderOAuthError(
                f"Error refreshing Snowflake token: {response_json}"
            )

        # Calculate expiration time if expires_in is provided
        expires_at = -1
        if "expires_in" in response_json:
            import time

            expires_at = int(time.time()) + int(response_json["expires_in"])

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": response_json.get(
                    "refresh_token", refresh_token
                ),  # Keep old refresh token if new one not provided
                "account_name": account_name,
            },
            expires_at=expires_at,
        )

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate Snowflake OAuth credentials by attempting a connection.
        """
        try:
            access_token = credentials.get("access_token")
            account_name = credentials.get("account_name")

            if not access_token:
                raise ToolProviderCredentialValidationError(
                    "Snowflake OAuth Access Token is required."
                )

            if not account_name:
                raise ToolProviderCredentialValidationError(
                    "Snowflake Account Name is required."
                )

            # Test connection with OAuth token
            import snowflake.connector

            conn = snowflake.connector.connect(
                account=account_name,
                authenticator="oauth",
                token=access_token,
                # Don't specify user - let OAuth determine the user
            )

            # Test basic query to validate connection
            cursor = conn.cursor()
            cursor.execute("SELECT CURRENT_USER()")
            cursor.fetchone()
            cursor.close()
            conn.close()

        except snowflake.connector.errors.DatabaseError as e:
            raise ToolProviderCredentialValidationError(
                f"Snowflake connection failed: {str(e)}"
            ) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
