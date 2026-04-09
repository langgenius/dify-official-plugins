from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import urllib.parse
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
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class WooCommerceTrigger(Trigger):
    """Dispatch WooCommerce webhook deliveries to Dify events."""

    _TOPIC_EVENT_MAP: dict[str, str] = {
        "order.created": "order_created",
        "order.updated": "order_updated",
        "order.deleted": "order_deleted",
        "product.created": "product_created",
        "product.updated": "product_updated",
        "product.deleted": "product_deleted",
        "customer.created": "customer_created",
        "customer.updated": "customer_updated",
        "customer.deleted": "customer_deleted",
        "coupon.created": "coupon_created",
        "coupon.updated": "coupon_updated",
        "coupon.deleted": "coupon_deleted",
    }

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        secret = self._resolve_webhook_secret(subscription)
        if secret:
            self._validate_signature(request=request, secret=secret)

        topic = request.headers.get("X-WC-Webhook-Topic") or ""
        topic = topic.strip().lower()
        if not topic:
            raise TriggerDispatchError("Missing WooCommerce webhook topic header")

        event_name = self._TOPIC_EVENT_MAP.get(topic)
        if not event_name:
            raise TriggerDispatchError(f"Unsupported WooCommerce webhook topic: {topic}")

        payload = self._parse_payload(request)
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        user_id = request.headers.get("X-WC-Webhook-Delivery-ID") or request.headers.get("X-WC-Webhook-ID")
        return EventDispatch(events=[event_name], response=response, payload=payload, user_id=user_id)

    @staticmethod
    def _resolve_webhook_secret(subscription: Subscription) -> str | None:
        if subscription.properties:
            secret = subscription.properties.get("webhook_secret")
            if secret:
                return str(secret)
        parameters = subscription.parameters or {}
        webhook_secret = parameters.get("webhook_secret")
        return str(webhook_secret) if webhook_secret else None

    @staticmethod
    def _parse_payload(request: Request) -> Mapping[str, Any]:
        try:
            payload = request.get_json(force=True)
        except Exception as exc:  # pragma: no cover - defensive
            raise TriggerDispatchError(f"Failed to parse WooCommerce payload: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise TriggerDispatchError("WooCommerce webhook payload must be a JSON object")
        return payload

    @staticmethod
    def _validate_signature(request: Request, secret: str) -> None:
        header_signature = request.headers.get("X-WC-Webhook-Signature")
        if not header_signature:
            raise TriggerValidationError("Missing WooCommerce webhook signature header")

        raw_body = request.get_data(cache=True)  # reuse body for get_json later
        computed = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
        encoded = base64.b64encode(computed).decode()
        if not hmac.compare_digest(header_signature, encoded):
            raise TriggerValidationError("Invalid WooCommerce webhook signature")


class WooCommerceSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Provision and manage WooCommerce webhook subscriptions."""

    _REQUEST_TIMEOUT = 15

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        response = self._http_request(
            method="GET",
            path="/webhooks",
            credentials=credentials,
            params={"per_page": 1},
            error_context="validation",
        )

        if response.status_code >= 400:
            message = self._format_error_message(response)
            raise TriggerProviderCredentialValidationError(
                f"WooCommerce credential validation failed: {message}"
            )

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        if credential_type != CredentialType.API_KEY:
            raise SubscriptionError(
                "WooCommerce trigger currently supports API Key credentials only.",
                error_code="UNSUPPORTED_CREDENTIAL_TYPE",
                external_response=None,
            )

        raw_topics = parameters.get("events") or []
        topics: list[str] = [str(topic) for topic in raw_topics if topic]
        if not topics:
            raise SubscriptionError(
                "Please select at least one WooCommerce event.",
                error_code="MISSING_EVENTS",
                external_response=None,
            )

        shared_secret = str(parameters.get("webhook_secret") or secrets.token_hex(32))
        webhooks: list[dict[str, Any]] = []

        for topic in topics:
            body = {
                "name": f"Dify {topic}",
                "topic": topic,
                "delivery_url": endpoint,
                "status": "active",
                "secret": shared_secret,
                "api_version": "wp_api_v3",
            }
            response = self._http_request(
                method="POST",
                path="/webhooks",
                credentials=credentials,
                json_data=body,
                error_context="subscription",
            )

            if response.status_code not in {200, 201}:
                message = self._format_error_message(response)
                raise SubscriptionError(
                    message=f"Failed to create WooCommerce webhook for topic '{topic}': {message}",
                    error_code="WEBHOOK_CREATION_FAILED",
                    external_response=self._safe_json(response),
                )

            data = self._safe_json(response)
            webhook_id = data.get("id")
            if not webhook_id:
                raise SubscriptionError(
                    message="WooCommerce API did not return a webhook id.",
                    error_code="MISSING_WEBHOOK_ID",
                    external_response=data,
                )

            webhooks.append({"id": str(webhook_id), "topic": data.get("topic", topic)})

        return Subscription(
            endpoint=endpoint,
            parameters=dict(parameters or {}),
            properties={
                "webhooks": webhooks,
                "webhook_secret": shared_secret,
                "events": topics,
            },
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        if credential_type != CredentialType.API_KEY:
            raise UnsubscribeError(
                message="WooCommerce trigger currently supports API Key credentials only.",
                error_code="UNSUPPORTED_CREDENTIAL_TYPE",
                external_response=None,
            )

        properties = subscription.properties or {}
        hooks: list[Mapping[str, Any]] = properties.get("webhooks") or []
        external_id = properties.get("external_id")
        if not hooks and external_id:
            hooks = [{"id": external_id}]
        if not hooks:
            raise UnsubscribeError(
                message="Missing WooCommerce webhook identifiers in subscription properties.",
                error_code="MISSING_WEBHOOK_ID",
                external_response=None,
            )

        for hook in hooks:
            hook_id = hook.get("id")
            if not hook_id:
                continue
            response = self._http_request(
                method="DELETE",
                path=f"/webhooks/{hook_id}",
                credentials=credentials,
                params={"force": True},
                error_context="unsubscribe",
            )
            if response.status_code not in {200, 204}:
                message = self._format_error_message(response)
                raise UnsubscribeError(
                    message=f"Failed to delete WooCommerce webhook {hook_id}: {message}",
                    error_code="WEBHOOK_DELETION_FAILED",
                    external_response=self._safe_json(response),
                )

        return UnsubscribeResult(success=True, message="WooCommerce webhooks deleted successfully")

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        # WooCommerce does not provide a lightweight refresh endpoint. Return the subscription unchanged.
        return Subscription(
            endpoint=subscription.endpoint,
            parameters=subscription.parameters,
            properties=subscription.properties,
        )

    def _http_request(
        self,
        *,
        method: str,
        path: str,
        credentials: Mapping[str, Any],
        params: Mapping[str, Any] | None = None,
        json_data: Mapping[str, Any] | None = None,
        error_context: str,
    ) -> httpx.Response:
        base_url, consumer_key, consumer_secret, include_in_query = self._extract_store_settings(
            credentials=credentials,
            error_context=error_context,
        )

        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{base_url}/wp-json/wc/v3{path}"

        query_params = dict(params or {})
        auth: tuple[str, str] | None = None
        if include_in_query:
            query_params["consumer_key"] = consumer_key
            query_params["consumer_secret"] = consumer_secret
        else:
            auth = (consumer_key, consumer_secret)

        headers = {"Accept": "application/json"}
        if json_data is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = httpx.request(
                method=method,
                url=url,
                params=query_params or None,
                json=json_data,
                auth=auth,
                headers=headers,
                timeout=self._REQUEST_TIMEOUT,
            )
        except Exception as exc:  # pragma: no cover - network guard
            self._raise_network_error(exc, error_context)

        return response

    def _extract_store_settings(
        self, credentials: Mapping[str, Any], error_context: str
    ) -> tuple[str, str, str, bool]:
        runtime_credentials = self.runtime.credentials if getattr(self, "runtime", None) else None
        store_url = credentials.get("url") or (runtime_credentials or {}).get("url")
        consumer_key = credentials.get("consumer_key") or (runtime_credentials or {}).get("consumer_key")
        consumer_secret = credentials.get("consumer_secret") or (runtime_credentials or {}).get("consumer_secret")
        include_in_query = bool(credentials.get("include_credentials_in_query") or (runtime_credentials or {}).get("include_credentials_in_query"))

        if not store_url:
            self._raise_missing_field("Store URL", error_context)
        if not consumer_key or not consumer_secret:
            self._raise_missing_field("Consumer Key and Consumer Secret", error_context)

        parsed = urllib.parse.urlparse(str(store_url))
        if not parsed.scheme or not parsed.netloc:
            self._raise_missing_field("Valid WooCommerce store URL", error_context)

        normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        return normalized_url.rstrip("/"), str(consumer_key), str(consumer_secret), include_in_query

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
        try:
            if response.content:
                return response.json()
        except json.JSONDecodeError:
            return {"raw": response.text}
        return None

    @staticmethod
    def _format_error_message(response: httpx.Response) -> str:
        payload = None
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {"raw": response.text}
        if isinstance(payload, Mapping):
            message = payload.get("message") or payload.get("error")
            if message:
                return str(message)
        return response.text or f"HTTP {response.status_code}"

    def _raise_network_error(self, exc: Exception, error_context: str) -> None:
        if error_context == "validation":
            raise TriggerProviderCredentialValidationError(
                f"Network error while calling WooCommerce API: {exc}"
            ) from exc
        if error_context == "unsubscribe":
            raise UnsubscribeError(
                message=f"Network error while deleting WooCommerce webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc
        raise SubscriptionError(
            message=f"Network error while calling WooCommerce API: {exc}",
            error_code="NETWORK_ERROR",
            external_response=None,
        ) from exc

    def _raise_missing_field(self, field: str, error_context: str) -> None:
        message = f"{field} is required for WooCommerce webhook management."
        if error_context == "validation":
            raise TriggerProviderCredentialValidationError(message)
        if error_context == "unsubscribe":
            raise UnsubscribeError(message=message, error_code="MISSING_CONFIGURATION", external_response=None)
        raise SubscriptionError(message=message, error_code="MISSING_CONFIGURATION", external_response=None)
