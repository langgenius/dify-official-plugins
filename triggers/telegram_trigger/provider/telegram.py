from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request, Response

from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class TelegramTrigger(Trigger):
    """Dispatch Telegram Bot API updates to matching trigger events."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        secret_token = subscription.properties.get("secret_token")
        if secret_token:
            header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if header_token != secret_token:
                raise TriggerValidationError("Invalid Telegram secret token")

        try:
            payload = request.get_json(force=True)
        except Exception as exc:  # pragma: no cover - defensive: werkzeug parsing errors
            raise TriggerDispatchError(f"Failed to parse Telegram payload: {exc}") from exc

        if not payload:
            raise TriggerDispatchError("Empty Telegram webhook payload")

        event = self._resolve_event(payload)
        response = Response(response='{"ok": true}', status=200, mimetype="application/json")
        if not event:
            return EventDispatch(events=[], response=response)
        return EventDispatch(events=[event], response=response)

    def _resolve_event(self, payload: Mapping[str, Any]) -> str:
        """Resolve Telegram update payload to a configured event name."""
        update_event_map = {
            "message": "message_received",
            "edited_message": "message_edited",
            "channel_post": "channel_post_created",
            "edited_channel_post": "channel_post_edited",
            "business_connection": "business_connection_updated",
            "business_message": "business_message_received",
            "edited_business_message": "business_message_edited",
            "deleted_business_messages": "business_messages_deleted",
            "message_reaction": "message_reaction_updated",
            "message_reaction_count": "message_reaction_count_updated",
            "inline_query": "inline_query_received",
            "chosen_inline_result": "inline_result_chosen",
            "callback_query": "callback_query_received",
            "shipping_query": "shipping_query_received",
            "pre_checkout_query": "pre_checkout_query_received",
            "poll": "poll_state_updated",
            "poll_answer": "poll_answer_received",
            "my_chat_member": "my_chat_member_updated",
            "chat_member": "chat_member_updated",
            "chat_join_request": "chat_join_request_received",
            "chat_boost": "chat_boost_updated",
            "removed_chat_boost": "chat_boost_removed",
        }
        for update_key, event_name in update_event_map.items():
            if update_key in payload:
                return event_name
        return ""


class TelegramSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Telegram Bot API webhook subscriptions."""

    _API_BASE = "https://api.telegram.org"

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        token = credentials.get("bot_token")
        if not token:
            raise TriggerProviderCredentialValidationError("Telegram Bot Token is required")

        url = f"{self._API_BASE}/bot{token}/getMe"
        try:
            response = requests.get(url, timeout=10)
        except requests.RequestException as exc:  # pragma: no cover - network error path
            raise TriggerProviderCredentialValidationError(f"Network error: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - invalid JSON path
            raise TriggerProviderCredentialValidationError("Invalid response from Telegram API") from exc

        if not payload.get("ok"):
            description = payload.get("description") or "Telegram API rejected the token"
            raise TriggerProviderCredentialValidationError(description)

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        token = credentials.get("bot_token")
        if not token:
            raise SubscriptionError("Telegram Bot Token is required", error_code="MISSING_BOT_TOKEN")

        allowed_updates = parameters.get("allowed_updates") or []
        secret_token = secrets.token_urlsafe(32)
        payload = {"url": endpoint, "secret_token": secret_token}
        if allowed_updates:
            payload["allowed_updates"] = allowed_updates

        response_data = self._telegram_post(token, "setWebhook", payload)
        if not response_data.get("result"):
            description = response_data.get("description") or "Failed to set Telegram webhook"
            raise SubscriptionError(
                description,
                error_code="SET_WEBHOOK_FAILED",
                external_response=response_data,
            )

        bot_profile = self._safe_get_bot_profile(token)
        webhook_info = self._safe_get_webhook_info(token)

        properties: dict[str, Any] = {
            "secret_token": secret_token,
            "allowed_updates": allowed_updates or webhook_info.get("allowed_updates", []),
            "webhook_url": webhook_info.get("url", endpoint),
        }
        if bot_profile:
            properties["bot_id"] = bot_profile.get("id")
            properties["bot_username"] = bot_profile.get("username")
            properties["bot_name"] = bot_profile.get("first_name")
        if webhook_info:
            for key in ("has_custom_certificate", "max_connections", "ip_address", "pending_update_count"):
                if key in webhook_info:
                    properties[key] = webhook_info[key]

        return Subscription(
            expires_at=-1,
            endpoint=endpoint,
            parameters=parameters,
            properties=properties,
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        token = credentials.get("bot_token")
        if not token:
            raise UnsubscribeError(
                message="Telegram Bot Token is required",
                error_code="MISSING_BOT_TOKEN",
            )

        response_data = self._telegram_post(token, "deleteWebhook", {"drop_pending_updates": True})
        if not response_data.get("ok"):
            description = response_data.get("description") or "Failed to delete Telegram webhook"
            raise UnsubscribeError(
                message=description,
                error_code="DELETE_WEBHOOK_FAILED",
                external_response=response_data,
            )

        message = response_data.get("description") or "Telegram webhook deleted"
        return UnsubscribeResult(success=True, message=message)

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        token = credentials.get("bot_token")
        if not token:
            raise SubscriptionError("Telegram Bot Token is required", error_code="MISSING_BOT_TOKEN")

        webhook_info = self._get_webhook_info(token)
        properties = dict(subscription.properties)
        for key in (
            "url",
            "has_custom_certificate",
            "pending_update_count",
            "ip_address",
            "max_connections",
            "allowed_updates",
        ):
            if key in webhook_info:
                target_key = "webhook_url" if key == "url" else key
                properties[target_key] = webhook_info[key]

        return Subscription(
            expires_at=-1,
            endpoint=subscription.endpoint,
            parameters=subscription.parameters,
            properties=properties,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _telegram_post(self, token: str, method: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        url = f"{self._API_BASE}/bot{token}/{method}"
        try:
            response = requests.post(url, json=payload, timeout=10)
        except requests.RequestException as exc:  # pragma: no cover - network error path
            raise SubscriptionError(
                f"Network error while calling Telegram {method}: {exc}",
                error_code="NETWORK_ERROR",
            ) from exc
        return self._parse_subscription_response(response, method)

    def _telegram_get(self, token: str, method: str) -> dict[str, Any]:
        url = f"{self._API_BASE}/bot{token}/{method}"
        try:
            response = requests.get(url, timeout=10)
        except requests.RequestException as exc:  # pragma: no cover - network error path
            raise SubscriptionError(
                f"Network error while calling Telegram {method}: {exc}",
                error_code="NETWORK_ERROR",
            ) from exc
        return self._parse_subscription_response(response, method)

    def _parse_subscription_response(self, response: requests.Response, method: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover - invalid JSON path
            raise SubscriptionError(
                "Invalid JSON response from Telegram API",
                error_code="INVALID_RESPONSE",
            ) from exc

        if not data.get("ok"):
            description = data.get("description") or f"Telegram API error during {method}"
            raise SubscriptionError(
                description,
                error_code="TELEGRAM_API_ERROR",
                external_response=data,
            )
        return data

    def _get_webhook_info(self, token: str) -> Mapping[str, Any]:
        response = self._telegram_get(token, "getWebhookInfo")
        return response.get("result") or {}

    def _safe_get_webhook_info(self, token: str) -> Mapping[str, Any]:
        try:
            return self._get_webhook_info(token)
        except SubscriptionError:
            return {}

    def _safe_get_bot_profile(self, token: str) -> Mapping[str, Any]:
        url = f"{self._API_BASE}/bot{token}/getMe"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            if data.get("ok"):
                return data.get("result") or {}
        except Exception:  # pragma: no cover - best effort path
            return {}
        return {}
