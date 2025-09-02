import secrets
import urllib.parse
from typing import Any, Mapping

import requests
from werkzeug import Request
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError


class DifyGmailProvider(ToolProvider):
    _GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
    _GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    _GMAIL_API_URL = "https://gmail.googleapis.com/gmail/v1"
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate Gmail OAuth credentials by making a test API call
        """
        try:
            access_token = credentials.get("access_token")
            if not access_token:
                raise ToolProviderCredentialValidationError("Access token is required")
            
            # Test the credentials by making a simple API call to get user profile
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            response = requests.get(
                f"{self._GMAIL_API_URL}/users/me/profile",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid or expired access token")
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(f"Gmail API error: {response.status_code}")
                
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Network error: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Credential validation failed: {str(e)}")
    
    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate the authorization URL for Gmail OAuth with comprehensive scopes
        """
        state = secrets.token_urlsafe(16)
        
        # Comprehensive Gmail scopes for full email management
        scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",      # Read emails
            "https://www.googleapis.com/auth/gmail.send",          # Send emails
            "https://www.googleapis.com/auth/gmail.compose",       # Create drafts
            "https://www.googleapis.com/auth/gmail.modify",        # Modify emails (labels, flags)
            "https://www.googleapis.com/auth/gmail.labels",        # Manage labels
        ]
        
        scope = " ".join(scopes)
        
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": scope,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        
        return f"{self._GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange authorization code for access token and refresh token
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("Authorization code not provided")
        
        error = request.args.get("error")
        if error:
            raise ToolProviderOAuthError(f"OAuth authorization failed: {error}")
        
        # Exchange code for tokens
        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = requests.post(
                self._GOOGLE_TOKEN_URL,
                data=data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            token_data = response.json()
            
            if "error" in token_data:
                raise ToolProviderOAuthError(f"Token exchange failed: {token_data.get('error_description', token_data['error'])}")
            
            access_token = token_data.get("access_token")
            if not access_token:
                raise ToolProviderOAuthError("No access token received from Google")
            
            credentials = {
                "access_token": access_token,
                "token_type": token_data.get("token_type", "Bearer"),
                "expires_in": str(token_data.get("expires_in", 3600)),
            }
            
            # Include refresh token if provided
            refresh_token = token_data.get("refresh_token")
            if refresh_token:
                credentials["refresh_token"] = refresh_token
            
            # Calculate expiration timestamp
            expires_in = token_data.get("expires_in", 3600)
            import time
            expires_at = int(time.time()) + expires_in
            
            return ToolOAuthCredentials(credentials=credentials, expires_at=expires_at)
            
        except requests.RequestException as e:
            raise ToolProviderOAuthError(f"Network error during token exchange: {str(e)}")
        except Exception as e:
            raise ToolProviderOAuthError(f"Failed to exchange authorization code: {str(e)}")

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        """
        Refresh the credentials using refresh token
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(
                self._GOOGLE_TOKEN_URL,
                data=data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            token_data = response.json()

            if "error" in token_data:
                raise ToolProviderOAuthError(f"Token refresh failed: {token_data.get('error_description', token_data['error'])}")

            access_token = token_data.get("access_token")
            if not access_token:
                raise ToolProviderOAuthError("No access token received from Google")

            new_credentials = {
                "access_token": access_token,
                "token_type": token_data.get("token_type", "Bearer"),
                "expires_in": str(token_data.get("expires_in", 3600)),
                "refresh_token": refresh_token,  # Keep existing refresh token
            }

            # Update refresh token if a new one is provided
            new_refresh_token = token_data.get("refresh_token")
            if new_refresh_token:
                new_credentials["refresh_token"] = new_refresh_token

            # Calculate expiration timestamp
            expires_in = token_data.get("expires_in", 3600)
            import time
            expires_at = int(time.time()) + expires_in

            return ToolOAuthCredentials(credentials=new_credentials, expires_at=expires_at)

        except requests.RequestException as e:
            raise ToolProviderOAuthError(f"Network error during token refresh: {str(e)}")
        except Exception as e:
            raise ToolProviderOAuthError(f"Failed to refresh credentials: {str(e)}") 