from typing import Any, Mapping
import time
import secrets
import urllib.parse

from dify_plugin.errors.tool import DatasourceOAuthError
from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
import requests
from flask import Request


class SharePointDatasourceProvider(DatasourceProvider):
    _API_BASE_URL = "https://graph.microsoft.com/v1.0"
    # SharePoint permission configuration - supports site-specific and general permissions
    _GENERAL_SCOPES = "openid offline_access User.Read Sites.Read.All Files.Read.All"

    def _get_tenant_id_for_auth(self, system_credentials: Mapping[str, Any]) -> str:
        """
        Get tenant ID for authorization from system credentials.
        Defaults to 'common' for multi-tenant apps if not specified.
        """
        return system_credentials.get("tenant_id") or "common"

    def _get_tenant_id_for_token(self, credentials: Mapping[str, Any]) -> str:
        """
        Get tenant ID for token refresh from saved credentials.
        For backward compatibility, defaults to 'common' if not saved.
        """
        return credentials.get("tenant_id") or "common"

    def _get_auth_url(self, tenant_id: str) -> str:
        """Get the OAuth authorization URL with the appropriate tenant ID."""
        return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"

    def _get_token_url(self, tenant_id: str) -> str:
        """Get the OAuth token URL with the appropriate tenant ID."""
        return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def _get_sharepoint_scopes(self, subdomain: str) -> str:
        """
        Generate SharePoint permission scopes based on subdomain
        Using Microsoft Graph API permissions as our implementation is based on Graph API
        """
        # Using Microsoft Graph permissions to support accessing Graph API endpoints
        # This allows simultaneous access to user information and SharePoint content
        return self._GENERAL_SCOPES
        # return f"openid offline_access User.Read https://{subdomain}.sharepoint.com/Sites.Read.All Files.Read.All"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        """Validate credential validity"""
        pass

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate SharePoint OAuth 2.0 authorization URL
        
        Args:
            redirect_uri: Redirect URI after authorization
            system_credentials: System credentials containing client_id, client_secret, and subdomain
            
        Returns:
            Authorization URL string
        """
        subdomain = system_credentials.get("subdomain")
        if not subdomain:
            raise DatasourceOAuthError("Missing SharePoint subdomain configuration")

        state = secrets.token_urlsafe(32)
        scopes = self._get_sharepoint_scopes(subdomain)
        tenant_id = self._get_tenant_id_for_auth(system_credentials)
        auth_url = self._get_auth_url(tenant_id)

        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
            "response_mode": "query"
        }
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """
        Exchange authorization code for access token
        
        Args:
            redirect_uri: Redirect URI
            system_credentials: System credentials containing client_id, client_secret, and subdomain
            request: Request object containing authorization code
            
        Returns:
            DatasourceOAuthCredentials object containing access token and refresh token
        """
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("Authorization code not provided")
            
        # Validate state parameter for security
        state = request.args.get("state")
        if not state:
            raise DatasourceOAuthError("Missing state parameter")

        # Get SharePoint subdomain
        subdomain = system_credentials.get("subdomain")
        if not subdomain:
            raise DatasourceOAuthError("Missing SharePoint subdomain configuration")

        # Get tenant ID for this authorization (will be saved to credentials)
        tenant_id = self._get_tenant_id_for_auth(system_credentials)

        # Use the same permission scopes as the authorization URL
        scopes = self._get_sharepoint_scopes(subdomain)
        token_url = self._get_token_url(tenant_id)

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "redirect_uri": redirect_uri,
            "scope": scopes
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        try:
            response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            
            access_token = response_data.get("access_token")
            refresh_token = response_data.get("refresh_token")
            expires_in = int(time.time()) + response_data.get("expires_in", 3600)
            
            if not access_token:
                raise DatasourceOAuthError(f"Failed to get access token: {response_data}")

            # Get user information
            userinfo_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            try:
                userinfo_response = requests.get(f"{self._API_BASE_URL}/me", headers=userinfo_headers, timeout=30)
                userinfo_response.raise_for_status()
                userinfo_json = userinfo_response.json()
            except requests.exceptions.RequestException as e:
                raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

            user_name = userinfo_json.get("displayName")
            user_email = userinfo_json.get("mail") or userinfo_json.get("userPrincipalName")
            user_picture = userinfo_json.get("photo", {}).get("@odata.mediaReadLink") if userinfo_json.get("photo") else None
                
            return DatasourceOAuthCredentials(
                name=user_name or user_email,
                avatar_url=user_picture,
                expires_at=expires_in,
                credentials={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": response_data.get("token_type", "bearer"),
                    "subdomain": subdomain,  # Save subdomain to credentials
                    "tenant_id": tenant_id,  # Save tenant_id to credentials for consistent token refresh
                },
            )
            
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to exchange authorization code for token: {str(e)}")

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        """
        Refresh access token using refresh token
        
        Args:
            redirect_uri: Redirect URI
            system_credentials: System credentials containing client_id, client_secret, and subdomain
            credentials: Current credentials containing refresh_token
            
        Returns:
            DatasourceOAuthCredentials object containing new access token
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("Refresh token not available")

        # Get subdomain (prefer from system credentials, then from current credentials)
        subdomain = system_credentials.get("subdomain") or credentials.get("subdomain")
        if not subdomain:
            raise DatasourceOAuthError("Missing SharePoint subdomain configuration")

        # Get tenant_id from saved credentials for consistent token refresh
        # For backward compatibility, defaults to "common" if not found
        tenant_id = self._get_tenant_id_for_token(credentials)

        # Use the same permission scopes as initial authorization
        scopes = self._get_sharepoint_scopes(subdomain)
        token_url = self._get_token_url(tenant_id)

        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "scope": scopes
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        try:
            response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
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
                userinfo_response = requests.get(f"{self._API_BASE_URL}/me", headers=userinfo_headers, timeout=30)
                userinfo_response.raise_for_status()
                userinfo_json = userinfo_response.json()
            except requests.exceptions.RequestException as e:
                raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

            user_name = userinfo_json.get("displayName")
            user_email = userinfo_json.get("mail") or userinfo_json.get("userPrincipalName")
            user_picture = userinfo_json.get("photo", {}).get("@odata.mediaReadLink") if userinfo_json.get("photo") else None

            updated_credentials = {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "token_type": response_data.get("token_type", "bearer"),
                "client_id": system_credentials.get("client_id") or credentials.get("client_id"),
                "client_secret": system_credentials.get("client_secret") or credentials.get("client_secret"),
                "subdomain": subdomain,
                "tenant_id": tenant_id,  # Keep the same tenant_id for consistent token refresh
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
                f"SSL error occurred while refreshing token. This may be caused by network proxy or firewall settings: {str(e)}"
            )
        except requests.exceptions.ConnectionError as e:
            raise DatasourceOAuthError(
                f"Connection error occurred while refreshing token. Please check your network connection: {str(e)}"
            )
        except requests.exceptions.Timeout as e:
            raise DatasourceOAuthError(
                f"Timeout occurred while refreshing token. Microsoft OAuth server may be slow to respond or inaccessible: {str(e)}"
            )
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to refresh token: {str(e)}")