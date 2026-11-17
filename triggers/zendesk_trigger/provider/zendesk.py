import base64
import hashlib
import hmac
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
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor

from events.utils import normalize_subdomain

# Internal event name -> Zendesk webhook event type.
# See https://developer.zendesk.com/api-reference/webhooks/event-types/webhook-event-types/
EVENT_TYPE_MAPPING: dict[str, str] = {
    "ticket_created": "zen:event-type:ticket.created",
    "ticket_status_changed": "zen:event-type:ticket.status_changed",
    "ticket_priority_changed": "zen:event-type:ticket.priority_changed",
    "ticket_comment_created": "zen:event-type:ticket.comment_added",
    "ticket_marked_as_spam": "zen:event-type:ticket.marked_as_spam",
    "article_published": "zen:event-type:article.published",
    "article_unpublished": "zen:event-type:article.unpublished",
}
ZENDESK_EVENT_TYPES: dict[str, str] = {value: key for key, value in EVENT_TYPE_MAPPING.items()}

_ERROR_HINTS: dict[int, str] = {
    401: "Zendesk could not authenticate the request. Check the subdomain, admin email and API token "
    "(or re-authorize the OAuth credential).",
    403: "The authenticated Zendesk user is not allowed to manage webhooks. An admin account is required.",
    404: "Resource not found. Check the Zendesk subdomain.",
    429: "Zendesk rate limit exceeded. Please retry later.",
}


def describe_zendesk_error(response: httpx.Response) -> str:
    """Build a readable error from a Zendesk API response; Zendesk often returns 401 with an empty body."""
    detail = ""
    try:
        data = response.json()
    except ValueError:
        data = None

    if isinstance(data, Mapping):
        errors = data.get("errors")
        error = data.get("error")
        if isinstance(errors, list):
            detail = "; ".join(
                ": ".join(str(part) for part in (err.get("title") or err.get("code"), err.get("detail")) if part)
                for err in errors
                if isinstance(err, Mapping)
            )
        elif isinstance(errors, Mapping):
            detail = json.dumps(errors, ensure_ascii=False)
        elif isinstance(error, Mapping):
            detail = str(error.get("message") or error.get("title") or "")
        elif error:
            description = data.get("description") or data.get("error_description")
            detail = f"{error}: {description}" if description else str(error)
    if not detail:
        detail = (response.text or "").strip()[:500]

    parts = [f"HTTP {response.status_code}"]
    if hint := _ERROR_HINTS.get(response.status_code):
        parts.append(hint)
    if detail:
        parts.append(detail)
    return " - ".join(parts)


def _safe_json(response: httpx.Response) -> Mapping[str, Any] | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, Mapping) else None


class ZendeskTrigger(Trigger):
    """Handle Zendesk webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        webhook_secret = (subscription.properties or {}).get("webhook_secret")
        if webhook_secret:
            self._verify_signature(secret=str(webhook_secret), request=request)

        payload: Mapping[str, Any] = self._validate_payload(request)
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        events: list[str] = self._dispatch_trigger_events(payload=payload)
        return EventDispatch(events=events, response=response, payload=payload)

    def _dispatch_trigger_events(self, payload: Mapping[str, Any]) -> list[str]:
        """Dispatch events based on Zendesk webhook payload.

        Zendesk webhook payload structure:
        {
            "type": "zen:event-type:ticket.comment_added",
            "detail": { ticket data },
            "event": { event specific data, e.g. "comment" or "current"/"previous" }
        }
        """
        event = ZENDESK_EVENT_TYPES.get(str(payload.get("type") or ""))
        return [event] if event else []

    def _validate_payload(self, request: Request) -> Mapping[str, Any]:
        try:
            payload = request.get_json(force=True)
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc
        if not payload or not isinstance(payload, Mapping):
            raise TriggerDispatchError("Empty request body")
        return payload

    @staticmethod
    def _verify_signature(secret: str, request: Request) -> None:
        signature = request.headers.get("X-Zendesk-Webhook-Signature")
        timestamp = request.headers.get("X-Zendesk-Webhook-Signature-Timestamp")
        if not signature or not timestamp:
            raise TriggerValidationError("Missing Zendesk webhook signature headers")

        body = request.get_data(cache=True, as_text=False)
        signed_payload = timestamp.encode("utf-8") + body
        digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("ascii")
        if not hmac.compare_digest(signature, expected):
            raise TriggerValidationError("Invalid Zendesk webhook signature")


class ZendeskSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Zendesk trigger subscriptions."""

    _AUTHORIZATION_PATH = "/oauth/authorizations/new"
    _TOKEN_PATH = "/oauth/tokens"
    _REQUEST_TIMEOUT = 15

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        api_token = str(credentials.get("api_token") or "").strip()
        email = str(credentials.get("email") or "").strip()
        runtime_credentials = self.runtime.credentials if getattr(self, "runtime", None) else None
        subdomain = normalize_subdomain(credentials.get("subdomain") or (runtime_credentials or {}).get("subdomain"))

        if not api_token or not email:
            raise TriggerProviderCredentialValidationError("Zendesk API Token and admin email are required.")
        if not subdomain:
            raise TriggerProviderCredentialValidationError("Zendesk subdomain is required.")

        # Webhook management is admin-only, so check the role up front instead of failing at subscribe time.
        url = f"https://{subdomain}.zendesk.com/api/v2/users/me.json"
        headers = {"Authorization": f"Basic {self._basic_auth(email, api_token)}"}
        try:
            response = httpx.get(url, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise TriggerProviderCredentialValidationError(f"Error while validating credentials: {exc}") from exc

        if response.status_code >= 400:
            raise TriggerProviderCredentialValidationError(
                f"Zendesk API token validation failed: {describe_zendesk_error(response)}"
            )

        user = (_safe_json(response) or {}).get("user") or {}
        if not user.get("id"):
            raise TriggerProviderCredentialValidationError(
                "Zendesk API token validation failed: the credentials resolved to an anonymous user. "
                "Check the admin email and API token."
            )
        if user.get("role") != "admin":
            raise TriggerProviderCredentialValidationError(
                f"Zendesk user {email} has role '{user.get('role')}', but managing webhooks requires an admin."
            )

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        subdomain = normalize_subdomain(system_credentials.get("subdomain"))
        if not subdomain:
            raise TriggerProviderOAuthError("Zendesk subdomain is required in the OAuth client configuration.")
        client_id = system_credentials.get("client_id")
        if not client_id:
            raise TriggerProviderOAuthError("Zendesk OAuth client_id is missing.")

        state = secrets.token_urlsafe(16)
        self._store_oauth_state(redirect_uri, state)
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

        self._validate_oauth_state(redirect_uri, request.args.get("state"))

        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("Zendesk OAuth callback missing authorization code.")

        subdomain = normalize_subdomain(system_credentials.get("subdomain"))
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
            "scope": "read write",
        }
        return self._exchange_token(subdomain=subdomain, payload=payload)

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> TriggerOAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("Zendesk OAuth refresh token is missing; please re-authorize.")

        subdomain = normalize_subdomain(credentials.get("subdomain") or system_credentials.get("subdomain"))
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
        events: list[str] = list(parameters.get("events") or [])
        zendesk_event_types = self._map_events_to_triggers(events)
        if not zendesk_event_types:
            raise SubscriptionError(
                "Select at least one Zendesk event to subscribe to.",
                error_code="NO_EVENTS_SELECTED",
                external_response=None,
            )

        subdomain, headers = self._build_authorization_headers(credentials, credential_type)
        base_url = f"https://{subdomain}.zendesk.com/api/v2/webhooks"

        # Zendesk generates the signing secret itself; admins cannot set it on creation.
        webhook_data = {
            "webhook": {
                "name": f"Dify Trigger - {uuid.uuid4().hex[:8]}",
                "status": "active",
                "endpoint": endpoint,
                "http_method": "POST",
                "request_format": "json",
                "subscriptions": zendesk_event_types,
            }
        }

        try:
            response = httpx.post(base_url, json=webhook_data, headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise SubscriptionError(
                f"Network error while creating Zendesk webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code not in (200, 201):
            raise SubscriptionError(
                f"Failed to create Zendesk webhook: {describe_zendesk_error(response)}",
                error_code="WEBHOOK_CREATION_FAILED",
                external_response=_safe_json(response),
            )

        webhook = (_safe_json(response) or {}).get("webhook") or {}
        webhook_id = str(webhook.get("id") or "")
        if not webhook_id:
            raise SubscriptionError(
                "Zendesk webhook was created but the response did not include its id.",
                error_code="WEBHOOK_CREATION_FAILED",
                external_response=_safe_json(response),
            )

        try:
            signing_secret = self._fetch_signing_secret(base_url, webhook_id, headers)
        except SubscriptionError:
            self._delete_webhook_quietly(base_url, webhook_id, headers)
            raise

        return Subscription(
            endpoint=endpoint,
            parameters=parameters,
            properties={
                "external_id": webhook_id,
                "events": events,
                "status": webhook.get("status", "active"),
                "subdomain": subdomain,
                "webhook_secret": signing_secret,
            },
        )

    def _fetch_signing_secret(self, base_url: str, webhook_id: str, headers: Mapping[str, str]) -> str:
        try:
            response = httpx.get(
                f"{base_url}/{webhook_id}/signing_secret", headers=headers, timeout=self._REQUEST_TIMEOUT
            )
        except httpx.HTTPError as exc:
            raise SubscriptionError(
                f"Network error while fetching Zendesk webhook signing secret: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        secret = ((_safe_json(response) or {}).get("signing_secret") or {}).get("secret")
        if response.status_code != 200 or not secret:
            raise SubscriptionError(
                f"Failed to fetch Zendesk webhook signing secret: {describe_zendesk_error(response)}",
                error_code="SIGNING_SECRET_FETCH_FAILED",
                external_response=_safe_json(response),
            )
        return str(secret)

    def _delete_webhook_quietly(self, base_url: str, webhook_id: str, headers: Mapping[str, str]) -> None:
        try:
            httpx.delete(f"{base_url}/{webhook_id}", headers=headers, timeout=self._REQUEST_TIMEOUT)
        except httpx.HTTPError:
            pass

    def _delete_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> UnsubscribeResult:
        external_id = (subscription.properties or {}).get("external_id")
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
        except httpx.HTTPError as exc:
            raise UnsubscribeError(
                message=f"Network error while deleting webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code in (200, 204):
            return UnsubscribeResult(success=True, message=f"Successfully removed webhook {external_id} from Zendesk")

        if response.status_code == 404:
            return UnsubscribeResult(success=True, message=f"Webhook {external_id} was already removed from Zendesk")

        raise UnsubscribeError(
            message=f"Failed to delete Zendesk webhook: {describe_zendesk_error(response)}",
            error_code="WEBHOOK_DELETION_FAILED",
            external_response=_safe_json(response),
        )

    def _refresh_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> Subscription:
        return Subscription(
            endpoint=subscription.endpoint,
            parameters=subscription.parameters,
            properties=subscription.properties,
        )

    def _map_events_to_triggers(self, events: list[str]) -> list[str]:
        """Map our internal event names to Zendesk webhook event types."""
        return [EVENT_TYPE_MAPPING[event] for event in events if event in EVENT_TYPE_MAPPING]

    @staticmethod
    def _basic_auth(email: str, api_token: str) -> str:
        return base64.b64encode(f"{email}/token:{api_token}".encode()).decode()

    def _build_authorization_headers(
        self, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> tuple[str, dict[str, str]]:
        runtime_credentials = self.runtime.credentials if getattr(self, "runtime", None) else None
        subdomain = normalize_subdomain(credentials.get("subdomain") or (runtime_credentials or {}).get("subdomain"))
        if not subdomain:
            raise SubscriptionError(
                "Zendesk subdomain is required to manage webhooks.",
                error_code="MISSING_SUBDOMAIN",
                external_response=None,
            )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if credential_type == CredentialType.API_KEY:
            api_token = str(credentials.get("api_token") or "").strip()
            email = str(credentials.get("email") or "").strip()
            if not api_token or not email:
                raise SubscriptionError(
                    "Zendesk API token credentials require both email and api_token.",
                    error_code="MISSING_CREDENTIALS",
                    external_response=None,
                )
            headers["Authorization"] = f"Basic {self._basic_auth(email, api_token)}"
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
        except httpx.HTTPError as exc:
            raise TriggerProviderOAuthError(f"Failed to reach Zendesk OAuth token endpoint: {exc}") from exc

        response_data = _safe_json(response)
        if response.status_code >= 400 or response_data is None:
            raise TriggerProviderOAuthError(f"Zendesk OAuth token request failed: {describe_zendesk_error(response)}")

        access_token = response_data.get("access_token")
        if not access_token:
            raise TriggerProviderOAuthError("Zendesk OAuth token response missing access_token.")

        expires_in: int | None = None
        try:
            expires_in = int(response_data.get("expires_in", 0)) or None
        except (TypeError, ValueError):
            expires_in = None

        expires_at = int(time.time()) + max(expires_in - 60, 0) if expires_in else -1

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

    def _oauth_state_key(self, redirect_uri: str, state: str) -> str:
        digest = hashlib.sha256(f"zendesk:{redirect_uri}:{state}".encode("utf-8")).hexdigest()
        return f"zendesk:oauth_state:{digest}"

    def _store_oauth_state(self, redirect_uri: str, state: str) -> None:
        try:
            self.runtime.session.storage.set(self._oauth_state_key(redirect_uri, state), b"1")
        except Exception as exc:
            raise TriggerProviderOAuthError("Unable to persist Zendesk OAuth state; storage permission is required.") from exc

    def _validate_oauth_state(self, redirect_uri: str, state: str | None) -> None:
        if not state:
            raise TriggerProviderOAuthError("Zendesk OAuth callback missing state.")
        key = self._oauth_state_key(redirect_uri, state)
        try:
            if not self.runtime.session.storage.exist(key):
                raise TriggerProviderOAuthError("Zendesk OAuth state is invalid or expired.")
            self.runtime.session.storage.delete(key)
        except TriggerProviderOAuthError:
            raise
        except Exception as exc:
            raise TriggerProviderOAuthError("Unable to validate Zendesk OAuth state.") from exc
