import secrets
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request

from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError


class FrontProvider(ToolProvider):
    _AUTH_URL = "https://app.frontapp.com/oauth/authorize"
    _TOKEN_URL = "https://app.frontapp.com/oauth/token"
    _API_BASE_URL = "https://api2.frontapp.com"
    _API_ME_URL = "https://api2.frontapp.com/me"

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate the authorization URL for the Front OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
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
        
        # Optionally validate state here
        state = request.args.get("state")
        if not state:
            raise ToolProviderOAuthError("No state parameter provided")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            response_json = response.json()
            
            access_token = response_json.get("access_token")
            if not access_token:
                raise ToolProviderOAuthError(f"Error in Front OAuth: {response_json}")

            return ToolOAuthCredentials(
                credentials={"access_token": access_token}, 
                expires_at=-1  # Front tokens don't expire
            )
            
        except requests.RequestException as e:
            raise ToolProviderOAuthError(f"Failed to exchange code for token: {str(e)}")

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        """
        Front tokens don't expire, so just return the existing credentials
        """
        return ToolOAuthCredentials(credentials=credentials, expires_at=-1)

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate the Front API credentials by making a test API call
        """
        try:
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("Front API Access Token is required.")
                
            headers = {
                "Authorization": f"Bearer {credentials['access_token']}",
                "Accept": "application/json",
            }
            
            response = requests.get(self._API_ME_URL, headers=headers, timeout=10)
            
            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid Front API token. Please re-authenticate.")
            elif response.status_code != 200:
                error_msg = "Unknown error"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                except:
                    error_msg = response.text or error_msg
                raise ToolProviderCredentialValidationError(f"Front API error: {error_msg}")
                
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Failed to validate Front credentials: {str(e)}")
        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Unexpected error validating credentials: {str(e)}")