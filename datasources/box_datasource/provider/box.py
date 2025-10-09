from typing import Any, Mapping
import certifi
import time
import secrets
import urllib.parse

from dify_plugin.errors.tool import ToolProviderCredentialValidationError, DatasourceOAuthError
from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Request


class BoxDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://account.box.com/api/oauth2/authorize"
    _TOKEN_URL = "https://api.box.com/oauth2/token"
    _API_BASE_URL = "https://api.box.com/2.0"
    _REQUIRED_SCOPES = "root_readwrite"  # Required for complete file operations

    def _get_requests_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.verify = certifi.where()
        return session

    # def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
    #     try:
    #         access_token = credentials.get("access_token")
    #         if not access_token:
    #             raise ToolProviderCredentialValidationError("Access token is required.")
    #         headers = {
    #             "Authorization": f"Bearer {access_token}",
    #             "Content-Type": "application/json",
    #         }

    #         session = self._get_requests_session()
    #         # Test API call to get user information
    #         response = session.get(f"{self._API_BASE_URL}/users/me", headers=headers, timeout=30)

    #         if response.status_code == 401:
    #             raise ToolProviderCredentialValidationError(
    #                 "Access token is invalid or expired. Please refresh or re-authorize."
    #             )
    #         elif response.status_code != 200:
    #             raise ToolProviderCredentialValidationError(
    #                 f"Failed to validate credentials: {response.status_code} {response.text}"
    #             )

    #         return None

    #     except requests.RequestException as e:
    #         raise ToolProviderCredentialValidationError(
    #             f"Network error when validating Box credentials: {str(e)}"
    #         )
    #     except Exception as e:
    #         raise ToolProviderCredentialValidationError(str(e))

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate the authorization URL for Box OAuth 2.0.
        
        Args:
            redirect_uri: The redirect URI after authorization
            system_credentials: System credentials containing client_id and client_secret
            
        Returns:
            Authorization URL string
        """
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._REQUIRED_SCOPES,
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """
        Exchange authorization code for access token.
        
        Args:
            redirect_uri: The redirect URI
            system_credentials: System credentials containing client_id and client_secret
            request: The request object containing the authorization code
            
        Returns:
            DatasourceOAuthCredentials object containing access and refresh tokens
        """
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("Authorization code not provided")
            
        # Validate state parameter for security
        state = request.args.get("state")
        if not state:
            raise DatasourceOAuthError("State parameter missing")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "redirect_uri": redirect_uri,
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        session = self._get_requests_session()
        try:
            response = session.post(self._TOKEN_URL, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            
            access_token = response_data.get("access_token")
            refresh_token = response_data.get("refresh_token")
            expires_in = int(time.time()) + response_data.get("expires_in", 3600)
            
            if not access_token:
                raise DatasourceOAuthError(f"Failed to obtain access token: {response_data}")

            # Get user information
            userinfo_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            try:
                userinfo_response = session.get(f"{self._API_BASE_URL}/users/me", headers=userinfo_headers, timeout=30)
                userinfo_response.raise_for_status()
                userinfo_json = userinfo_response.json()
            except requests.exceptions.RequestException as e:
                raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

            user_name = userinfo_json.get("name")
            user_email = userinfo_json.get("login")
            user_picture = None  # Box API doesn't provide profile picture in user info
                
            return DatasourceOAuthCredentials(
                name=user_name or user_email,
                avatar_url=user_picture,
                expires_at=expires_in,
                credentials={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": response_data.get("token_type", "bearer")
                },
            )
            
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to exchange code for token: {str(e)}")

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        """
        Refresh the access token using refresh token.
        
        Args:
            redirect_uri: The redirect URI
            system_credentials: System credentials containing client_id and client_secret
            credentials: Current credentials containing refresh_token
            
        Returns:
            DatasourceOAuthCredentials object with new access token
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("Refresh token not available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        session = self._get_requests_session()
        try:
            response = session.post(self._TOKEN_URL, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            
            access_token = response_data.get("access_token")
            new_refresh_token = response_data.get("refresh_token", refresh_token)
            expires_in = int(time.time()) + response_data.get("expires_in", 3600)
            
            if not access_token:
                raise DatasourceOAuthError(f"Failed to refresh access token: {response_data}")

            # Get user information
            userinfo_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            try:
                userinfo_response = session.get(f"{self._API_BASE_URL}/users/me", headers=userinfo_headers, timeout=30)
                userinfo_response.raise_for_status()
                userinfo_json = userinfo_response.json()
            except requests.exceptions.RequestException as e:
                raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

            user_name = userinfo_json.get("name")
            user_email = userinfo_json.get("login")
            user_picture = None  # Box API doesn't provide profile picture in user info

            updated_credentials = {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "token_type": response_data.get("token_type", "bearer"),
                "client_id": system_credentials.get("client_id") or credentials.get("client_id"),
                "client_secret": system_credentials.get("client_secret") or credentials.get("client_secret"),
                "user_email": user_email,
            }
                
            return DatasourceOAuthCredentials(
                name=user_name or user_email,
                avatar_url=user_picture,
                expires_at=expires_in,
                credentials=updated_credentials,
            )
            
        except requests.exceptions.SSLError as e:
            raise DatasourceOAuthError(
                f"SSL error when refreshing token. This might be due to network proxy or firewall settings: {str(e)}"
            )
        except requests.exceptions.ConnectionError as e:
            raise DatasourceOAuthError(
                f"Connection error when refreshing token. Please check your network connection: {str(e)}"
            )
        except requests.exceptions.Timeout as e:
            raise DatasourceOAuthError(
                f"Timeout when refreshing token. The Box OAuth server might be slow or unreachable: {str(e)}"
            )
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to refresh token: {str(e)}")