import base64
import json
import uuid
from collections.abc import Mapping
from typing import Any

import httpx
from werkzeug import Request, Response

from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
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

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        api_token = credentials.get("api_token")
        email = credentials.get("email")
        subdomain = credentials.get("subdomain")

        url = f"https://{subdomain}.zendesk.com/api/v2/webhooks"
        auth_string = f"{email}/token:{api_token}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
        }
        try:
            httpx.get(url, headers=headers, timeout=10)
        except Exception as exc:
            raise TriggerProviderCredentialValidationError(
                f"error while validating credentials: {exc}"
            )

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

        api_token = credentials.get("api_token")
        email = credentials.get("email")
        subdomain = credentials.get("subdomain")

        # Create webhook using Zendesk API
        # Note: Zendesk uses webhooks via triggers, which is more complex
        # For simplicity, we're creating a webhook endpoint
        url = f"https://{subdomain}.zendesk.com/api/v2/webhooks"

        auth_string = f"{email}/token:{api_token}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
        }

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

        try:
            response = httpx.post(url, json=webhook_data, headers=headers, timeout=10)
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
                    "webhook_secret": "abcdef", 
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

        api_token = credentials.get("api_token")
        email = credentials.get("email")
        subdomain = credentials.get("subdomain")

        auth_string = f"{email}/token:{api_token}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()

        url = f"https://{subdomain}.zendesk.com/api/v2/webhooks/{external_id}"
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.delete(url, headers=headers, timeout=10)
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
        zendesk_triggers = [event_mapping.get(e) for e in events]
        return zendesk_triggers
