import secrets
import time
import urllib.parse
from typing import Any, Mapping

import requests
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from hubspot import HubSpot
from hubspot.crm.contacts.exceptions import ApiException

_AUTH_URL = "https://app.hubspot.com/oauth/authorize"
_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
_DEFAULT_SCOPE = (
    "crm.objects.contacts.read crm.objects.contacts.write "
    "crm.objects.companies.read crm.objects.companies.write "
    "crm.objects.deals.read crm.objects.deals.write "
    "crm.objects.tickets.read crm.objects.tickets.write"
)


class HubspotProvider(ToolProvider):
    """HubSpot Provider - supports both a Private App access token and OAuth 2.0."""

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate credentials by making a read-only test call.

        Works for both auth paths: a manually-entered Private App token and an
        OAuth access token are both stored under `access_token`.
        """
        try:
            if not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("HubSpot access token is required.")
            client = HubSpot(access_token=credentials.get("access_token"))
            client.crm.contacts.basic_api.get_page(limit=1)
        except ApiException as e:
            raise ToolProviderCredentialValidationError(f"Invalid HubSpot token: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to connect to HubSpot: {str(e)}")

    # --- OAuth 2.0 (public-app / multi-account) ---
    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": system_credentials.get("scope") or _DEFAULT_SCOPE,
            "state": secrets.token_urlsafe(16),
        }
        return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Any
    ) -> ToolOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError("No authorization code provided by HubSpot.")
        data = {
            "grant_type": "authorization_code",
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "redirect_uri": redirect_uri,
            "code": code,
        }
        resp = requests.post(_TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Token exchange failed: {resp.text}")
        token = resp.json()
        return ToolOAuthCredentials(
            credentials={
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token"),
            },
            expires_at=int(time.time()) + int(token.get("expires_in", 1800)),
        )

    def oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:
        data = {
            "grant_type": "refresh_token",
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": credentials.get("refresh_token"),
        }
        resp = requests.post(_TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Token refresh failed: {resp.text}")
        token = resp.json()
        return ToolOAuthCredentials(
            credentials={
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token", credentials.get("refresh_token")),
            },
            expires_at=int(time.time()) + int(token.get("expires_in", 1800)),
        )
