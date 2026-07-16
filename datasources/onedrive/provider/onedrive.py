import time
import urllib.parse
from typing import Any, Mapping

import requests
from dify_plugin.errors.tool import DatasourceOAuthError
from dify_plugin.interfaces.datasource import DatasourceOAuthCredentials, DatasourceProvider
from flask import Request


class OneDriveDatasourceProvider(DatasourceProvider):
    _AUTHORITY_URL = "https://login.microsoftonline.com"
    _DEFAULT_TENANT_ID = "organizations"
    _DEFAULT_EXPIRES_IN = 3600
    _SCOPES = "offline_access User.Read Files.Read Files.Read.All"
    _USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        pass

    def _tenant_id(self, credentials: Mapping[str, Any]) -> str:
        tenant_id = str(credentials.get("tenant_id") or self._DEFAULT_TENANT_ID).strip()
        return tenant_id or self._DEFAULT_TENANT_ID

    def _tenant_path(self, credentials: Mapping[str, Any]) -> str:
        return urllib.parse.quote(self._tenant_id(credentials), safe="")

    def _authorization_endpoint(self, credentials: Mapping[str, Any]) -> str:
        return f"{self._AUTHORITY_URL}/{self._tenant_path(credentials)}/oauth2/v2.0/authorize"

    def _token_endpoint(self, credentials: Mapping[str, Any]) -> str:
        return f"{self._AUTHORITY_URL}/{self._tenant_path(credentials)}/oauth2/v2.0/token"

    def _expires_at(self, expires_in: Any) -> int:
        ttl = expires_in if expires_in is not None else self._DEFAULT_EXPIRES_IN
        return int(time.time()) + max(int(ttl) - 60, 0)

    def _response_json(self, response: requests.Response, endpoint: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise DatasourceOAuthError(f"Microsoft {endpoint} endpoint returned invalid JSON") from exc
        return payload if isinstance(payload, dict) else {}

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        if not system_credentials.get("client_id"):
            raise DatasourceOAuthError("Missing Microsoft client_id configuration")

        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": self._SCOPES,
            "response_mode": "query",
        }
        return f"{self._authorization_endpoint(system_credentials)}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("No code provided")

        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise DatasourceOAuthError("Missing Microsoft client_id or client_secret configuration")

        tenant_id = self._tenant_id(system_credentials)

        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
            "scope": self._SCOPES,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            token_response = requests.post(
                self._token_endpoint(system_credentials),
                data=token_data,
                headers=headers,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise DatasourceOAuthError(f"Network error during Microsoft token exchange: {exc}") from exc
        if token_response.status_code >= 400:
            raise DatasourceOAuthError(
                f"Microsoft token endpoint error: {token_response.status_code} {token_response.text}"
            )
        token_json = self._response_json(token_response, "token")
        access_token = token_json.get("access_token")
        refresh_token = token_json.get("refresh_token")
        expires_in = token_json.get("expires_in")
        if not access_token:
            raise DatasourceOAuthError(f"Error in Microsoft OAuth token exchange: {token_json}")
        if not refresh_token:
            raise DatasourceOAuthError("Microsoft OAuth response missing refresh_token")

        userinfo_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            userinfo_resp = requests.get(self._USERINFO_URL, headers=userinfo_headers, timeout=10)
        except requests.RequestException as exc:
            raise DatasourceOAuthError(f"Network error during Microsoft userinfo request: {exc}") from exc
        if userinfo_resp.status_code >= 400:
            raise DatasourceOAuthError(
                f"Microsoft userinfo endpoint error: {userinfo_resp.status_code} {userinfo_resp.text}"
            )
        user = self._response_json(userinfo_resp, "userinfo")

        return DatasourceOAuthCredentials(
            name=user.get("displayName") or user.get("userPrincipalName"),
            avatar_url=None,
            expires_at=self._expires_at(expires_in),
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "tenant_id": tenant_id,
                "user_email": user.get("userPrincipalName"),
            },
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("Missing refresh_token for token refresh")

        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise DatasourceOAuthError("Missing Microsoft client_id or client_secret configuration")

        tenant_id = self._tenant_id({"tenant_id": credentials.get("tenant_id") or system_credentials.get("tenant_id")})
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": self._SCOPES,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            token_response = requests.post(
                self._token_endpoint({"tenant_id": tenant_id}),
                data=token_data,
                headers=headers,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise DatasourceOAuthError(f"Network error during Microsoft token refresh: {exc}") from exc
        if token_response.status_code >= 400:
            raise DatasourceOAuthError(
                f"Microsoft token refresh endpoint error: {token_response.status_code} {token_response.text}"
            )

        token_json = self._response_json(token_response, "token refresh")
        access_token = token_json.get("access_token")
        if not access_token:
            raise DatasourceOAuthError(f"Error in Microsoft OAuth token refresh: {token_json}")

        expires_in = token_json.get("expires_in")
        new_refresh_token = token_json.get("refresh_token") or refresh_token

        return DatasourceOAuthCredentials(
            name=credentials.get("user_email") or "OneDrive",
            avatar_url=None,
            expires_at=self._expires_at(expires_in),
            credentials={
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "tenant_id": tenant_id,
                "user_email": credentials.get("user_email"),
            },
        )
