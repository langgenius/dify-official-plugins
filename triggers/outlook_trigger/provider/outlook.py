from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
import time
import urllib.parse
import uuid
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request, Response

from dify_plugin.entities.oauth import TriggerOAuthCredentials
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerProviderOAuthError,
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _extract_error(response: requests.Response) -> str:
    payload = _safe_json(response)
    error = payload.get("error")
    if isinstance(error, Mapping):
        message = error.get("message") or error.get("code")
        if message:
            return str(message)
    message = payload.get("error_description") or payload.get("message") or payload.get("error")
    return str(message or response.text or f"HTTP {response.status_code}")[:500]


def _get_access_token(credentials: Mapping[str, Any] | None) -> str | None:
    if not credentials:
        return None
    token = credentials.get("access_tokens") or credentials.get("access_token")
    return str(token) if token else None


class OutlookTrigger(Trigger):
    """Handle Outlook webhook event dispatch."""

    def _dispatch_event(
        self, subscription: Subscription, request: Request
    ) -> EventDispatch:
        properties = subscription.properties or {}
        client_state = properties.get("client_state")

        body = request.get_data()

        if len(body) == 0:  # validation request
            validationToken = request.args.get("validationToken")
            if validationToken:
                returnText = urllib.parse.unquote(validationToken)
                return EventDispatch(events=[], response=Response(response=returnText, status=200, mimetype="application/text"))
            return EventDispatch(events=[], response=Response(response="", status=202, mimetype="application/text"))
        else:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise TriggerDispatchError(f"Invalid Outlook notification JSON: {exc}") from exc

            values = payload.get("value")
            if not isinstance(values, list) or not values:
                raise TriggerDispatchError("Outlook notification missing value array")
            value = values[0]
            if not isinstance(value, Mapping):
                raise TriggerDispatchError("Outlook notification value must be an object")

            resource_data = value.get("resourceData")
            if not isinstance(resource_data, Mapping):
                raise TriggerDispatchError("Outlook notification missing resourceData")

            message_id = resource_data.get("id")
            if not message_id:
                raise TriggerDispatchError("Outlook notification missing resourceData.id")

            # check if the email is already processed
            if self._is_email_processed(str(message_id)):
                return EventDispatch(events=[], response=Response(response="Email already processed", status=200, mimetype="application/text"))

            resource = value.get("resource")
            if not resource:
                raise TriggerDispatchError("Outlook notification missing resource")

            if value.get("clientState") != client_state:
                raise TriggerDispatchError("Invalid client state")
            
            events = ["email_received"]

            fetch_url = f"https://graph.microsoft.com/v1.0/{resource}"
            access_token = _get_access_token(self.runtime.credentials if self.runtime else None) or _get_access_token(properties)
            if not access_token:
                raise TriggerDispatchError("Missing Outlook OAuth access token")
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
            try:
                response = requests.get(fetch_url, headers=headers, timeout=10)
            except requests.RequestException as exc:
                raise TriggerDispatchError(f"Network error while fetching Outlook resource: {exc}") from exc
            if response.status_code == 200:
                data = _safe_json(response)
                
                response = Response(response='Accepted', status=202, mimetype="application/text")

                events = ["email_received"]
                return EventDispatch(events=events, response=response, payload=data)
            else:
                raise TriggerDispatchError(f"Failed to fetch resource: {_extract_error(response)}")

    def _is_email_processed(self, id: str) -> bool:
        processed = self.runtime.session.storage.exist(f"email_processed_{id}")

        if processed:
            return True
        else:
            self.runtime.session.storage.set(f"email_processed_{id}", b'1')
            return False


class OutlookSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Outlook trigger subscriptions."""

    _AUTHORITY_URL = "https://login.microsoftonline.com"
    _DEFAULT_TENANT_ID = "organizations"
    _DEFAULT_SCOPE = "offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Read.Shared"
    _API_ME_URL = "https://graph.microsoft.com/v1.0/me"
    _WEBHOOK_TTL = 3 * 24 * 60 * 60

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        access_token = _get_access_token(credentials)
        if not access_token:
            raise TriggerProviderCredentialValidationError("Outlook access token is required.")

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            response = requests.get(self._API_ME_URL, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise TriggerProviderCredentialValidationError(f"Failed to validate Outlook credentials: {exc}") from exc
        if response.status_code != 200:
            raise TriggerProviderCredentialValidationError(f"Outlook credential validation failed: {_extract_error(response)}")

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        client_id = system_credentials.get("client_id")
        if not client_id:
            raise TriggerProviderOAuthError("Outlook OAuth client_id is missing.")

        state = secrets.token_urlsafe(16)
        self._store_oauth_state(redirect_uri, state)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": system_credentials.get("scope", self._DEFAULT_SCOPE),
            "response_type": "code",
            "state": state,
        }
        return f"{self._auth_url(system_credentials)}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> TriggerOAuthCredentials:
        error = request.args.get("error")
        if error:
            description = request.args.get("error_description") or ""
            raise TriggerProviderOAuthError(f"Outlook OAuth authorization failed: {error}: {description}".strip(": "))

        self._validate_oauth_state(redirect_uri, request.args.get("state"))

        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("No code provided")

        if not system_credentials.get("client_id") or not system_credentials.get(
            "client_secret"
        ):
            raise TriggerProviderOAuthError("Client ID or Client Secret is required")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": system_credentials.get("scope", self._DEFAULT_SCOPE),
        }
        headers = {"Accept": "application/json"}
        try:
            response = requests.post(self._token_url(system_credentials), data=data, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise TriggerProviderOAuthError(f"Network error during Outlook OAuth token exchange: {exc}") from exc
        response_json = _safe_json(response)
        if response.status_code >= 400:
            raise TriggerProviderOAuthError(f"Outlook OAuth token exchange failed: {_extract_error(response)}")
        access_tokens = response_json.get("access_token")
        if not access_tokens:
            raise TriggerProviderOAuthError("Outlook OAuth response missing access_token")
        refresh_token = response_json.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("No refresh token in response")
        expires_in = response_json.get("expires_in")
        expires_at = max(int(expires_in if expires_in is not None else 3599) - 60, 0) + int(time.time())

        return TriggerOAuthCredentials(
            credentials={
                "access_tokens": access_tokens,
                "refresh_token": refresh_token,
                "tenant_id": self._tenant_id(system_credentials),
            },
            expires_at=expires_at,
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> TriggerOAuthCredentials:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("Outlook refresh token is missing; please re-authorize.")
        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise TriggerProviderOAuthError("Client ID or Client Secret is required")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        tenant_credentials = {"tenant_id": credentials.get("tenant_id") or system_credentials.get("tenant_id")}
        try:
            response = requests.post(self._token_url(tenant_credentials), headers=headers, data=data, timeout=10)
        except requests.RequestException as exc:
            raise TriggerProviderOAuthError(f"Network error during Outlook OAuth refresh: {exc}") from exc
        payload = _safe_json(response)
        if response.status_code == 200:
            access_tokens = payload.get("access_token")
            if not access_tokens:
                raise TriggerProviderOAuthError("Outlook OAuth refresh response missing access_token")
            expires_in = payload.get("expires_in")
            expires_at = max(int(expires_in if expires_in is not None else 3599) - 60, 0) + int(time.time())
            return TriggerOAuthCredentials(
                credentials={
                    "access_tokens": access_tokens,
                    "refresh_token": payload.get("refresh_token") or refresh_token,
                    "tenant_id": self._tenant_id(tenant_credentials),
                },
                expires_at=expires_at,
            )
        else:
            raise TriggerProviderOAuthError(f"Failed to refresh Outlook access token: {_extract_error(response)}")

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:

        url = "https://graph.microsoft.com/v1.0/subscriptions"
        access_token = _get_access_token(credentials)
        if not access_token:
            raise SubscriptionError("Missing Outlook OAuth access token", error_code="MISSING_ACCESS_TOKEN")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        client_state = secrets.token_urlsafe(16)
        # 72 hours from now
        expiration_date = datetime.now() + timedelta(seconds=self._WEBHOOK_TTL)
        expiration_date_str = expiration_date.isoformat() + "Z"

        # Monitor a shared mailbox if provided, otherwise the signed-in user's own inbox
        mailbox_address = str(parameters.get("mailbox_address") or "").strip()
        if mailbox_address:
            resource = f"users/{urllib.parse.quote(mailbox_address, safe='@')}/mailFolders('Inbox')/messages"
        else:
            resource = "me/mailfolders('Inbox')/messages"

        data = {
            "changeType": "created,updated",
            "notificationUrl": endpoint,
            "resource": resource,
            "expirationDateTime": expiration_date_str,
            "clientState": client_state,
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                message=f"Network error while creating subscription: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc
            
        if response.status_code == 201:
            subscription = _safe_json(response)
            return Subscription(
                expires_at=int(time.time()) + self._WEBHOOK_TTL,
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "subscription_id": subscription.get("id"),
                    "client_state": client_state,
                },
            )
        else:
            response_data = _safe_json(response)
            raise SubscriptionError(
                message=f"Failed to create subscription: {_extract_error(response)}",
                error_code="SUBSCRIPTION_CREATION_FAILED",
                external_response=response_data,
            )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        subscription_id = subscription.properties.get("subscription_id")
        if not subscription_id:
            return UnsubscribeResult(success=True, message="Missing Outlook subscription ID; subscription already removed.")
        
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        access_token = _get_access_token(credentials)
        if not access_token:
            return UnsubscribeResult(success=False, message="Missing Outlook OAuth access token")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        try:
            response = requests.delete(url, headers=headers, timeout=10)
        except requests.RequestException as exc:
            return UnsubscribeResult(success=False, message=f"Network error while deleting Outlook subscription: {exc}")
        if response.status_code == 204:
            return UnsubscribeResult(success=True, message=f"Successfully deleted subscription {subscription_id}")
        if response.status_code == 404:
            return UnsubscribeResult(success=True, message=f"Outlook subscription {subscription_id} was already removed")
        else:
            raise UnsubscribeError(
                message=f"Failed to delete subscription: {_extract_error(response)}",
                error_code="SUBSCRIPTION_DELETION_FAILED",
                external_response=_safe_json(response),
            )

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        new_expiration_date = datetime.now() + timedelta(seconds=self._WEBHOOK_TTL)
        new_expiration_date_str = new_expiration_date.isoformat() + "Z"

        subscription_id = subscription.properties.get("subscription_id")
        if not subscription_id:
            raise UnsubscribeError(
                message="Missing subscription ID",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        access_token = _get_access_token(credentials)
        if not access_token:
            raise SubscriptionError("Missing Outlook OAuth access token", error_code="MISSING_ACCESS_TOKEN")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        data = {
            "expirationDateTime": new_expiration_date_str,
        }
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        try:
            response = requests.patch(url, headers=headers, json=data, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                f"Network error while refreshing Outlook subscription: {exc}",
                error_code="NETWORK_ERROR",
            ) from exc
        if response.status_code == 200:
            properties = dict(subscription.properties or {})
            properties.update(
                {
                    "subscription_id": subscription_id,
                    "client_state": properties.get("client_state"),
                }
            )
            properties.pop("access_tokens", None)
            properties.pop("refresh_token", None)
            return Subscription(
                expires_at=int(new_expiration_date.timestamp()),
                endpoint=subscription.endpoint,
                properties=properties,
            )
        else:
            raise SubscriptionError(
                message=f"Failed to refresh subscription: {_extract_error(response)}",
                error_code="SUBSCRIPTION_REFRESH_FAILED",
                external_response=_safe_json(response),
            )

    def _tenant_id(self, system_credentials: Mapping[str, Any]) -> str:
        tenant_id = str(system_credentials.get("tenant_id") or self._DEFAULT_TENANT_ID).strip()
        return tenant_id or self._DEFAULT_TENANT_ID

    def _tenant_path(self, system_credentials: Mapping[str, Any]) -> str:
        return urllib.parse.quote(self._tenant_id(system_credentials), safe="")

    def _auth_url(self, system_credentials: Mapping[str, Any]) -> str:
        return f"{self._AUTHORITY_URL}/{self._tenant_path(system_credentials)}/oauth2/v2.0/authorize"

    def _token_url(self, system_credentials: Mapping[str, Any]) -> str:
        return f"{self._AUTHORITY_URL}/{self._tenant_path(system_credentials)}/oauth2/v2.0/token"

    def _oauth_state_key(self, redirect_uri: str, state: str) -> str:
        import hashlib

        digest = hashlib.sha256(f"outlook:{redirect_uri}:{state}".encode("utf-8")).hexdigest()
        return f"outlook:oauth_state:{digest}"

    def _store_oauth_state(self, redirect_uri: str, state: str) -> None:
        try:
            self.runtime.session.storage.set(self._oauth_state_key(redirect_uri, state), b"1")
        except Exception as exc:
            raise TriggerProviderOAuthError("Unable to persist Outlook OAuth state; storage permission is required.") from exc

    def _validate_oauth_state(self, redirect_uri: str, state: str | None) -> None:
        if not state:
            raise TriggerProviderOAuthError("Outlook OAuth callback missing state.")
        key = self._oauth_state_key(redirect_uri, state)
        try:
            if not self.runtime.session.storage.exist(key):
                raise TriggerProviderOAuthError("Outlook OAuth state is invalid or expired.")
            self.runtime.session.storage.delete(key)
        except TriggerProviderOAuthError:
            raise
        except Exception as exc:
            raise TriggerProviderOAuthError("Unable to validate Outlook OAuth state.") from exc
