import base64
import json
import secrets
import time
import urllib.parse
import uuid
from collections.abc import Mapping
from typing import Any

import httpx
from werkzeug import Request, Response

from dify_plugin.entities.oauth import TriggerOAuthCredentials
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerProviderOAuthError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class ZendeskTrigger(Trigger):
    """Handle Zendesk webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        payload: Mapping[str, Any] = self._validate_payload(request)
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        events: list[str] = self._dispatch_trigger_events(payload=payload)
        return EventDispatch(events=events, response=response)

    def _dispatch_trigger_events(self, payload: Mapping[str, Any]) -> list[str]:
        """Dispatch events based on Zendesk webhook payload.

        Zendesk webhook payload structure:
        {
            "type": "zen:event-type:ticket.custom_status_changed",
            "detail": { ticket data },
            "event": { "current": ..., "previous": ... }
        }
        """
        events = []

        # Get the event type from the payload
        event_type = payload.get("type", "")

        # Map Zendesk event types to our internal event names
        if event_type.startswith("zen:event-type:ticket."):
            # Extract the specific ticket event
            ticket_event = event_type.replace("zen:event-type:ticket.", "")

            if ticket_event == "created":
                events.append("ticket_created")
            elif ticket_event == "marked_as_spam":
                events.append("ticket_marked_as_spam")
            elif ticket_event == "status_changed":
                events.append("ticket_status_changed")
            elif ticket_event == "priority_changed":
                events.append("ticket_priority_changed")
            elif ticket_event == "comment_created":
                events.append("ticket_comment_created")

        elif event_type.startswith("zen:event-type:article."):
            article_event = event_type.replace("zen:event-type:article.", "")

            if article_event == "published":
                events.append("article_published")
            elif article_event == "unpublished":
                events.append("article_unpublished")

        return events

    def _validate_payload(self, request: Request) -> Mapping[str, Any]:
        try:
            payload = request.get_json(force=True)
            if not payload:
                raise TriggerDispatchError("Empty request body")
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc


class ZendeskSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Zendesk trigger subscriptions."""

    _AUTHORIZATION_PATH = "/oauth/authorizations/new"
    _TOKEN_PATH = "/oauth/tokens"
    _REQUEST_TIMEOUT = 15

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        api_token = credentials.get("api_token")
        email = credentials.get("email")
        runtime_credentials = self.runtime.credentials if getattr(self, "runtime", None) else None
        subdomain = credentials.get("subdomain") or (runtime_credentials or {}).get("subdomain")

        if not api_token or not email:
            raise TriggerProviderCredentialValidationError("Zendesk API Token and admin email are required.")
        if not subdomain:
            raise TriggerProviderCredentialValidationError("Zendesk subdomain is required.")

        url = f"https://{subdomain}.zendesk.com/api/v2/webhooks"
        auth_string = f"{email}/token:{api_token}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.get(url, headers=headers, timeout=10)
        except Exception as exc:
            raise TriggerProviderCredentialValidationError(
                f"error while validating credentials: {exc}"
            )
        if response.status_code >= 400:
            try:
                details = response.json()
            except json.JSONDecodeError:
                details = {"message": response.text}
            raise TriggerProviderCredentialValidationError(
                f"Zendesk API token validation failed: {details.get('error', details.get('message', response.text))}"
            )

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        subdomain = system_credentials.get("subdomain")
        if not subdomain:
            raise TriggerProviderOAuthError("Zendesk subdomain is required in the OAuth client configuration.")
        client_id = system_credentials.get("client_id")
        if not client_id:
            raise TriggerProviderOAuthError("Zendesk OAuth client_id is missing.")

        state = secrets.token_urlsafe(16)
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "read write",
        }

        base_url = f"https://{subdomain}.zendesk.com{self._AUTHORIZATION_PATH}"
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> TriggerOAuthCredentials:
        error = request.args.get("error")
        if error:
            description = request.args.get("error_description") or ""
            message = f"{error}: {description}".strip(": ")
            raise TriggerProviderOAuthError(f"Zendesk OAuth authorization failed: {message}")

        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("Zendesk OAuth callback missing authorization code.")

        subdomain = system_credentials.get("subdomain")
        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not subdomain or not client_id or not client_secret:
            raise TriggerProviderOAuthError("Zendesk OAuth client configuration is incomplete.")

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        return self._exchange_token(subdomain=subdomain, payload=payload)

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> TriggerOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("Zendesk OAuth refresh token is missing; please re-authorize.")

        subdomain = credentials.get("subdomain") or system_credentials.get("subdomain")
        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not subdomain or not client_id or not client_secret:
            raise TriggerProviderOAuthError("Zendesk OAuth client configuration is incomplete.")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        return self._exchange_token(subdomain=subdomain, payload=payload)

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:

        events: list[str] = parameters.get("events", [])

        # Map our internal event names to Zendesk webhook trigger events
        zendesk_triggers = self._map_events_to_triggers(events)

        subdomain, headers = self._build_authorization_headers(credentials, credential_type)

        # Create webhook using Zendesk API
        # Note: Zendesk uses webhooks via triggers, which is more complex
        # For simplicity, we're creating a webhook endpoint
        url = f"https://{subdomain}.zendesk.com/api/v2/webhooks"

        user_defined_secret = parameters.get("webhook_secret")
        webhook_data = {
            "webhook": {
                "name": f"Dify Webhook - {uuid.uuid4().hex[:8]}",
                "status": "active",
                "endpoint": endpoint,
                "http_method": "POST",
                "request_format": "json",
                "subscriptions": zendesk_triggers,
            }
        }
        if user_defined_secret:
            webhook_data["webhook"]["signing_secret"] = user_defined_secret

        try:
            response = httpx.post(url, json=webhook_data, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.RequestException as exc:
            raise SubscriptionError(
                f"Network error while creating webhook: {exc}", error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code == 201:
            webhook = response.json().get("webhook", {})
            webhook_id = str(webhook["id"])

            return Subscription(
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "external_id": webhook_id,
                    "events": events,
                    "status": webhook.get("status", "active"),
                    "webhook_secret": user_defined_secret,
                },
            )

        response_data: dict[str, Any] = response.json() if response.content else {}
        error_msg = json.dumps(response_data)

        raise SubscriptionError(
            f"Failed to create Zendesk webhook: {error_msg}",
            error_code="WEBHOOK_CREATION_FAILED",
            external_response=response_data,
        )

    def _delete_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> UnsubscribeResult:
        external_id = subscription.properties.get("external_id")
        if not external_id:
            raise UnsubscribeError(
                message="Missing webhook ID information",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        subdomain, headers = self._build_authorization_headers(credentials, credential_type)
        url = f"https://{subdomain}.zendesk.com/api/v2/webhooks/{external_id}"

        try:
            response = httpx.delete(url, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.RequestException as exc:
            raise UnsubscribeError(
                message=f"Network error while deleting webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code == 204:
            return UnsubscribeResult(
                success=True, message=f"Successfully removed webhook {external_id} from Zendesk"
            )

        if response.status_code == 404:
            raise UnsubscribeError(
                message=f"Webhook {external_id} not found in Zendesk",
                error_code="WEBHOOK_NOT_FOUND",
                external_response=response.json() if response.content else None,
            )

        raise UnsubscribeError(
            message=f"Failed to delete webhook: {response.text}",
            error_code="WEBHOOK_DELETION_FAILED",
            external_response=response.json() if response.content else None,
        )

    def _refresh_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> Subscription:
        return Subscription(
            endpoint=subscription.endpoint,
            properties=subscription.properties,
        )

    def _map_events_to_triggers(self, events: list[str]) -> list[str]:
        """Map our internal event names to Zendesk webhook trigger types."""
        event_mapping = {
            "ticket_created": "zen:event-type:ticket.created",
            "ticket_status_changed": "zen:event-type:ticket.status_changed",
            "ticket_priority_changed": "zen:event-type:ticket.priority_changed",
            "ticket_comment_created": "zen:event-type:ticket.comment_added",
            "ticket_marked_as_spam": "zen:event-type:ticket.marked_as_spam",
            "article_published": "zen:event-type:article.published",
            "article_unpublished": "zen:event-type:article.unpublished",
        }
        return [event_mapping[e] for e in events if event_mapping.get(e)]

    def _build_authorization_headers(
        self, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> tuple[str, dict[str, str]]:
        runtime_credentials = self.runtime.credentials if getattr(self, "runtime", None) else None
        subdomain = credentials.get("subdomain") or (runtime_credentials or {}).get("subdomain")
        if not subdomain:
            raise SubscriptionError(
                "Zendesk subdomain is required to manage webhooks.",
                error_code="MISSING_SUBDOMAIN",
                external_response=None,
            )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if credential_type == CredentialType.API_KEY:
            api_token = credentials.get("api_token")
            email = credentials.get("email")
            if not api_token or not email:
                raise SubscriptionError(
                    "Zendesk API token credentials require both email and api_token.",
                    error_code="MISSING_CREDENTIALS",
                    external_response=None,
                )
            auth_string = f"{email}/token:{api_token}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            headers["Authorization"] = f"Basic {encoded_auth}"
        elif credential_type == CredentialType.OAUTH:
            access_token = credentials.get("access_token")
            if not access_token:
                raise SubscriptionError(
                    "Zendesk OAuth credentials require an access_token.",
                    error_code="MISSING_CREDENTIALS",
                    external_response=None,
                )
            headers["Authorization"] = f"Bearer {access_token}"
        else:
            raise SubscriptionError(
                f"Unsupported Zendesk credential type: {credential_type.value}",
                error_code="UNSUPPORTED_CREDENTIAL_TYPE",
                external_response=None,
            )

        return subdomain, headers

    def _exchange_token(self, subdomain: str, payload: Mapping[str, Any]) -> TriggerOAuthCredentials:
        url = f"https://{subdomain}.zendesk.com{self._TOKEN_PATH}"

        try:
            response = httpx.post(url, json=payload, timeout=self._REQUEST_TIMEOUT)
        except httpx.RequestException as exc:
            raise TriggerProviderOAuthError(f"Failed to reach Zendesk OAuth token endpoint: {exc}") from exc

        try:
            response_data = response.json()
        except json.JSONDecodeError as exc:
            raise TriggerProviderOAuthError(
                f"Invalid response from Zendesk OAuth token endpoint: {response.text}"
            ) from exc

        if response.status_code >= 400:
            error_description = response_data.get("error_description") or response_data.get("error")
            raise TriggerProviderOAuthError(
                f"Zendesk OAuth token request failed: {error_description or response.text}"
            )

        access_token = response_data.get("access_token")
        if not access_token:
            raise TriggerProviderOAuthError("Zendesk OAuth token response missing access_token.")

        expires_in: int | None = None
        try:
            expires_in = int(response_data.get("expires_in", 0)) or None
        except (TypeError, ValueError):
            expires_in = None

        expires_at = int(time.time()) + expires_in if expires_in else -1

        credentials: dict[str, Any] = {
            "access_token": access_token,
            "refresh_token": response_data.get("refresh_token"),
            "scope": response_data.get("scope"),
            "token_type": response_data.get("token_type"),
            "subdomain": subdomain,
        }
        # Clean out None values to keep stored credentials compact
        filtered_credentials = {key: value for key, value in credentials.items() if value}

        return TriggerOAuthCredentials(credentials=filtered_credentials, expires_at=expires_at)
