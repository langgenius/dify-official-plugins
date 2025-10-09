from typing import Any, Mapping
import certifi
import time

from dify_plugin.errors.tool import ToolProviderCredentialValidationError, DatasourceOAuthError
from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.parse
from flask import Request


class GoogleDriveDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

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

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            access_token = credentials.get("access_token")
            if not access_token:
                raise ToolProviderCredentialValidationError("Access token is required.")
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            session = self._get_requests_session()
            response = session.get(self._USERINFO_URL, headers=headers, timeout=30)

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Access token is invalid or expired. Please refresh or re-authorize."
                )
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"Failed to validate credentials: {response.status_code} {response.text}"
                )

            return None

        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Network error when validating Google Drive credentials: {str(e)}"
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
        ]
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """
        Use the authorization code (code) to get the access token and user information.
        """
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("No code provided")

        token_data = {
            "code": code,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json"}

        session = self._get_requests_session()
        try:
            token_response = session.post(self._TOKEN_URL, data=token_data, headers=headers, timeout=30)
            token_response.raise_for_status()
            token_response_json = token_response.json()
        except requests.exceptions.RequestException as e:
            raise DatasourceOAuthError(f"Failed to exchange authorization code for token: {str(e)}")

        access_token = token_response_json.get("access_token")
        refresh_token = token_response_json.get("refresh_token")
        expires_in = int(time.time()) + token_response_json.get("expires_in", 3600)

        if not access_token:
            raise DatasourceOAuthError(f"Error in Google OAuth token exchange: {token_response_json}")

        userinfo_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            userinfo_response = session.get(self._USERINFO_URL, headers=userinfo_headers, timeout=30)
            userinfo_response.raise_for_status()
            userinfo_json = userinfo_response.json()
        except requests.exceptions.RequestException as e:
            raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

        user_name = userinfo_json.get("name")
        user_picture = userinfo_json.get("picture")
        user_email = userinfo_json.get("email")

        return DatasourceOAuthCredentials(
            name=user_name or user_email,
            avatar_url=user_picture,
            expires_at=expires_in,
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("No refresh token available. Please re-authorize.")
        token_data = {
            "refresh_token": refresh_token,
            "client_id": system_credentials.get("client_id") or credentials.get("client_id"),
            "client_secret": system_credentials.get("client_secret") or credentials.get("client_secret"),
            "grant_type": "refresh_token",
        }

        headers = {"Accept": "application/json"}
        session = self._get_requests_session()
        try:
            token_response = session.post(self._TOKEN_URL, data=token_data, headers=headers, timeout=30)
            token_response.raise_for_status()
            token_response_json = token_response.json()
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
                f"Timeout when refreshing token. The Google OAuth server might be slow or unreachable: {str(e)}"
            )
        except requests.exceptions.RequestException as e:
            raise DatasourceOAuthError(f"Failed to refresh token: {str(e)}")

        expires_in = int(time.time()) + token_response_json.get("expires_in", 3600)
        new_access_token = token_response_json.get("access_token")
        if not new_access_token:
            raise DatasourceOAuthError(f"Failed to get new access token: {token_response_json}")
        userinfo_headers = {
            "Authorization": f"Bearer {new_access_token}",
            "Accept": "application/json",
        }

        try:
            userinfo_response = session.get(self._USERINFO_URL, headers=userinfo_headers, timeout=30)
            userinfo_response.raise_for_status()
            userinfo_json = userinfo_response.json()
        except requests.exceptions.RequestException as e:
            raise DatasourceOAuthError(f"Failed to get user info: {str(e)}")

        user_name = userinfo_json.get("name")
        user_picture = userinfo_json.get("picture")
        user_email = userinfo_json.get("email")

        updated_credentials = {
            "access_token": new_access_token,
            "refresh_token": refresh_token,
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
