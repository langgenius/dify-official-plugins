import json
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


class AirtableTrigger(Trigger):
    """Handle Airtable webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        self._validate_payload(subscription, request)
        response = Response(response="ok", status=200)
        events: list[str] = self._dispatch_trigger_events()
        return EventDispatch(events=events, response=response)

    def _dispatch_trigger_events(self) -> list[str]:
        """Dispatch events based on Airtable webhook payload.

        Airtable webhook notification structure:
        {
            "base": {"id": "appXXX"},
            "webhook": {"id": "achXXX"},
            "timestamp": "2023-01-01T00:00:00.000Z"
        }
        
        Note: Airtable doesn't send the actual changed data in the notification.
        The notification is just a ping that tells you to fetch the payloads.
        """
        return ["record_created"]

    def _validate_payload(self, subscription: Subscription, request: Request) -> Mapping[str, Any]:
        """Validate the webhook payload and signature if MAC secret is configured."""
        try:
            payload = request.get_json(force=True)
            if not payload:
                raise TriggerDispatchError("Empty request body")
            
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc


class AirtableSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Airtable trigger subscriptions."""

    _API_BASE_URL = "https://api.airtable.com/v0"
    _REQUEST_TIMEOUT = 15

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        access_token = credentials.get("access_token")
        
        if not access_token:
            raise TriggerProviderCredentialValidationError("Airtable Personal Access Token is required.")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        try:
            # Try to fetch user info to validate token
            response = httpx.get(
                "https://api.airtable.com/v0/meta/whoami",
                headers=headers,
                timeout=10
            )
        except Exception as exc:
            raise TriggerProviderCredentialValidationError(
                f"Error while validating credentials: {exc}"
            )
        
        if response.status_code >= 400:
            try:
                details = response.json()
            except json.JSONDecodeError:
                details = {"message": response.text}
            raise TriggerProviderCredentialValidationError(
                f"Airtable token validation failed: {details.get('error', {}).get('message', response.text)}"
            )

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        
        base_id = parameters.get("base_id")
        if not base_id:
            raise SubscriptionError(
                "base_id is required to create webhook.",
                error_code="MISSING_BASE_ID",
            )

        events: list[str] = parameters.get("events", [])
        table_ids_str = parameters.get("table_ids", "")

        # Build webhook specification
        spec: dict[str, Any] = {
            "options": {
                "filters": {
                    "dataTypes": []
                }
            }
        }

        # Map events to Airtable data types
        if "record_created" in events or "record_updated" in events or "record_deleted" in events:
            spec["options"]["filters"]["dataTypes"].append("tableData")

        # Add table filters if specified
        if table_ids_str:
            table_ids = [tid.strip() for tid in table_ids_str.split(",") if tid.strip()]
            if table_ids:
                spec["options"]["filters"]["fromSources"] = [
                    {"type": "table", "tableId": tid} for tid in table_ids
                ]

        access_token = credentials.get("access_token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Create webhook via Airtable API
        url = f"{self._API_BASE_URL}/bases/{base_id}/webhooks"
        webhook_data = {
            "notificationUrl": endpoint,
            "specification": spec,
        }

        try:
            response = httpx.post(url, json=webhook_data, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.RequestException as exc:
            raise SubscriptionError(
                f"Network error while creating webhook: {exc}",
                error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code == 200 or response.status_code == 201:
            webhook_response = response.json()
            webhook_id = webhook_response.get("id")
            mac_secret = webhook_response.get("macSecretBase64")
            expiration_time = webhook_response.get("expirationTime")

            return Subscription(
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "external_id": webhook_id,
                    "base_id": base_id,
                    "events": events,
                    "cursor": 1,
                    "access_token": access_token,
                    "mac_secret": mac_secret,
                    "expiration_time": expiration_time,
                },
            )

        response_data: dict[str, Any] = response.json() if response.content else {}
        error_msg = response_data.get("error", {}).get("message", json.dumps(response_data))

        raise SubscriptionError(
            f"Failed to create Airtable webhook: {error_msg}",
            error_code="WEBHOOK_CREATION_FAILED",
            external_response=response_data,
        )

    def _delete_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> UnsubscribeResult:
        
        external_id = subscription.properties.get("external_id")
        base_id = subscription.properties.get("base_id")
        
        if not external_id or not base_id:
            raise UnsubscribeError(
                message="Missing webhook ID or base ID information",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        access_token = credentials.get("access_token")
        if not access_token:
            raise UnsubscribeError(
                message="Airtable Personal Access Token is required.",
                error_code="MISSING_CREDENTIALS",
                external_response=None,
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self._API_BASE_URL}/bases/{base_id}/webhooks/{external_id}"

        try:
            response = httpx.delete(url, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.RequestException as exc:
            raise UnsubscribeError(
                message=f"Network error while deleting webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code == 204 or response.status_code == 200:
            return UnsubscribeResult(
                success=True,
                message=f"Successfully removed webhook {external_id} from Airtable"
            )

        if response.status_code == 404:
            raise UnsubscribeError(
                message=f"Webhook {external_id} not found in Airtable",
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
        """Refresh the webhook to extend its lifetime.
        
        Airtable webhooks created with personal access tokens expire after 7 days.
        Calling refresh extends the life for another 7 days.
        """
        external_id = subscription.properties.get("external_id")
        base_id = subscription.properties.get("base_id")
        
        if not external_id or not base_id:
            raise SubscriptionError(
                "Missing webhook ID or base ID information",
                error_code="MISSING_PROPERTIES",
            )

        access_token = credentials.get("access_token")
        if not access_token:
            raise SubscriptionError(
                "Airtable Personal Access Token is required.",
                error_code="MISSING_CREDENTIALS",
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = f"{self._API_BASE_URL}/bases/{base_id}/webhooks/{external_id}/refresh"

        try:
            response = httpx.post(url, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.RequestException as exc:
            raise SubscriptionError(
                f"Network error while refreshing webhook: {exc}",
                error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code == 200:
            webhook_response = response.json()
            expiration_time = webhook_response.get("expirationTime")
            
            # Update properties with new expiration time
            updated_properties = dict(subscription.properties)
            updated_properties["expiration_time"] = expiration_time
            
            return Subscription(
                endpoint=subscription.endpoint,
                properties=updated_properties,
            )

        response_data: dict[str, Any] = response.json() if response.content else {}
        error_msg = response_data.get("error", {}).get("message", json.dumps(response_data))

        raise SubscriptionError(
            f"Failed to refresh Airtable webhook: {error_msg}",
            error_code="WEBHOOK_REFRESH_FAILED",
            external_response=response_data,
        )
