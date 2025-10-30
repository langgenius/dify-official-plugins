"""Typeform trigger provider implementation."""

from __future__ import annotations

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

import requests
from werkzeug import Request, Response

from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.oauth import TriggerOAuthCredentials
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerProviderOAuthError,
    TriggerValidationError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor

_SUPPORTED_EVENT_TYPES: dict[str, str] = {
    "form_response": "form_response_received",
}


class TypeformTrigger(Trigger):
    """Dispatch Typeform webhook events."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        raw_body = request.get_data()
        if raw_body is None:
            raise TriggerDispatchError("Missing request body")

        secret = subscription.properties.get("webhook_secret")
        if secret:
            self._verify_signature(secret=secret, request=request, raw_body=raw_body)

        payload = self._parse_payload(raw_body)

        event_type = payload.get("event_type")
        if not isinstance(event_type, str):
            raise TriggerDispatchError("Missing event_type in payload")

        mapped_event = _SUPPORTED_EVENT_TYPES.get(event_type)
        if mapped_event is None:
            raise TriggerDispatchError(f"Unsupported Typeform event_type: {event_type}")

        form_id_filter = subscription.properties.get("form_id")
        if form_id_filter:
            form_response = payload.get("form_response")
            target_form_id = None
            if isinstance(form_response, Mapping):
                target_form_id = form_response.get("form_id")

            if target_form_id != form_id_filter:
                response = Response(response='{"status": "ignored"}', status=200, mimetype="application/json")
                return EventDispatch(events=[], response=response, payload=payload)

        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        return EventDispatch(events=[mapped_event], response=response, payload=payload)

    @staticmethod
    def _parse_payload(raw_body: bytes) -> Mapping[str, Any]:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - unexpected JSON errors
            raise TriggerDispatchError(f"Failed to parse JSON payload: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise TriggerDispatchError("Payload must be a JSON object")
        if not payload:
            raise TriggerDispatchError("Empty payload")
        return payload

    @staticmethod
    def _verify_signature(*, secret: str, request: Request, raw_body: bytes) -> None:
        header = request.headers.get("Typeform-Signature")
        if not header:
            raise TriggerValidationError("Missing Typeform-Signature header")

        prefix = "sha256="
        if not header.startswith(prefix):
            raise TriggerValidationError("Unsupported signature format")

        digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        expected = prefix + base64.b64encode(digest).decode("ascii")

        if not hmac.compare_digest(header, expected):
            raise TriggerValidationError("Invalid webhook signature")


class TypeformSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Store Typeform webhook subscription metadata."""

    _API_BASE = "https://api.typeform.com"
    _OAUTH_AUTHORIZE_URL = f"{_API_BASE}/oauth/authorize"
    _OAUTH_TOKEN_URL = f"{_API_BASE}/oauth/token"
    _DEFAULT_SCOPES = ["forms:read", "webhooks:read", "webhooks:write", "offline"]
    _WEBHOOK_SECRET_BYTES = 32

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        token = self._get_token_for_validation(credentials)
        try:
            response = self._api_request(
                method="GET",
                path="/forms",
                token=token,
                expected_status={200},
                params={"page_size": 1},
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure guard
            raise TriggerProviderCredentialValidationError(f"Failed to reach Typeform API: {exc}") from exc

        if response.status_code != 200:
            message = self._extract_error_message(response)
            raise TriggerProviderCredentialValidationError(f"Typeform API token validation failed: {message}")

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        form_id = self._normalize_optional_string(parameters.get("form_id"))
        webhook_secret = self._normalize_optional_string(parameters.get("webhook_secret"))

        if webhook_secret and not isinstance(webhook_secret, str):
            raise SubscriptionError("webhook_secret must be a string", error_code="invalid_secret")

        if form_id and not isinstance(form_id, str):
            raise SubscriptionError("form_id must be a string", error_code="invalid_form_id")

        if credential_type == CredentialType.UNAUTHORIZED:
            return Subscription(
                expires_at=-1,
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "form_id": form_id,
                    "webhook_secret": webhook_secret,
                },
            )

        token = self._get_required_token(credentials, credential_type)
        token_type = self._get_token_type(credentials)

        normalized_form_id = self._require_form_id(form_id)
        managed_secret = webhook_secret or secrets.token_hex(self._WEBHOOK_SECRET_BYTES)
        webhook_tag = self._generate_webhook_tag(normalized_form_id)

        form_title = self._fetch_form_title(
            form_id=normalized_form_id,
            token=token,
            token_type=token_type,
        )

        webhook_data = self._upsert_webhook(
            form_id=normalized_form_id,
            webhook_tag=webhook_tag,
            endpoint=endpoint,
            secret=managed_secret,
            token=token,
            token_type=token_type,
        )

        return Subscription(
            expires_at=-1,
            endpoint=endpoint,
            parameters=parameters,
            properties={
                "form_id": normalized_form_id,
                "form_title": form_title,
                "webhook_secret": managed_secret,
                "webhook_tag": webhook_tag,
                "webhook_status": webhook_data.get("enabled"),
                "webhook_url": webhook_data.get("url"),
                "managed_by": "dify",
            },
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        if credential_type == CredentialType.UNAUTHORIZED:
            return UnsubscribeResult(success=True, message="Subscription removed (manual webhook).")

        form_id = subscription.properties.get("form_id")
        webhook_tag = subscription.properties.get("webhook_tag")
        if not form_id or not webhook_tag:
            return UnsubscribeResult(success=True, message="No managed Typeform webhook to delete.")

        try:
            token = self._get_required_token(credentials, credential_type)
        except SubscriptionError as exc:
            return UnsubscribeResult(success=False, message=str(exc))

        try:
            token_type = self._get_token_type(credentials)
            response = self._api_request(
                method="DELETE",
                path=f"/forms/{form_id}/webhooks/{webhook_tag}",
                token=token,
                token_type=token_type,
                expected_status={200, 202, 204, 404},
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure guard
            return UnsubscribeResult(
                success=False,
                message=f"Failed to reach Typeform API while deleting webhook: {exc}",
            )

        if response.status_code == 404:
            return UnsubscribeResult(success=True, message="Webhook already removed in Typeform.")

        if response.status_code in {200, 202, 204}:
            return UnsubscribeResult(success=True, message="Typeform webhook deleted.")

        message = self._extract_error_message(response)
        return UnsubscribeResult(success=False, message=f"Failed to delete Typeform webhook: {message}")

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        # Webhooks do not expire automatically.
        return subscription

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        client_id = self._normalize_optional_string(system_credentials.get("client_id"))
        if not client_id:
            raise TriggerProviderOAuthError("client_id is required for Typeform OAuth.")

        state = secrets.token_urlsafe(16)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._DEFAULT_SCOPES),
            "state": state,
        }
        return f"{self._OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        request: Request,
    ) -> TriggerOAuthCredentials:
        code = self._normalize_optional_string(request.args.get("code"))
        if not code:
            raise TriggerProviderOAuthError("Missing authorization code in callback.")

        client_id = self._normalize_optional_string(system_credentials.get("client_id"))
        client_secret = self._normalize_optional_string(system_credentials.get("client_secret"))
        if not client_id or not client_secret:
            raise TriggerProviderOAuthError("client_id and client_secret are required for OAuth token exchange.")

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        token_response = self._exchange_token(payload)
        return self._build_oauth_credentials(token_response)

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> TriggerOAuthCredentials:
        refresh_token = self._normalize_optional_string(credentials.get("refresh_token"))
        if not refresh_token:
            raise TriggerProviderOAuthError("Missing refresh_token for OAuth refresh.")

        client_id = self._normalize_optional_string(system_credentials.get("client_id"))
        client_secret = self._normalize_optional_string(system_credentials.get("client_secret"))
        if not client_id or not client_secret:
            raise TriggerProviderOAuthError("client_id and client_secret are required for OAuth refresh.")

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        token_response = self._exchange_token(payload)
        return self._build_oauth_credentials(token_response, fallback_refresh_token=refresh_token)

    def _fetch_parameter_options(
        self,
        parameter: str,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> list[ParameterOption]:
        if parameter != "form_id":
            return []

        token = self._normalize_optional_string(credentials.get("access_token"))
        if not token:
            raise ValueError("Missing Typeform access token for fetching forms.")

        token_type = self._get_token_type(credentials)

        try:
            forms = self._list_forms(token=token, token_type=token_type)
        except ValueError as exc:
            raise exc
        except requests.RequestException as exc:  # pragma: no cover - network failure guard
            raise ValueError(f"Failed to reach Typeform API: {exc}") from exc

        options: list[ParameterOption] = []
        for form in forms:
            form_id = form.get("id")
            if not isinstance(form_id, str):
                continue
            title = form.get("title") or "Untitled form"
            workspace = form.get("workspace", {})
            workspace_name = workspace.get("name")
            label_text = title
            if workspace_name:
                label_text = f"{title} — {workspace_name}"

            options.append(
                ParameterOption(
                    value=form_id,
                    label=I18nObject(en_US=f"{label_text} ({form_id})"),
                    icon=form.get("_links", {}).get("display") if isinstance(form.get("_links"), Mapping) else None,
                )
            )

        return options

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _list_forms(
        self,
        *,
        token: str,
        token_type: str | None,
    ) -> list[Mapping[str, Any]]:
        page = 1
        forms: list[Mapping[str, Any]] = []
        while True:
            response = self._api_request(
                method="GET",
                path="/forms",
                token=token,
                token_type=token_type,
                params={"page": page, "page_size": 200},
            )
            if response.status_code != 200:
                message = self._extract_error_message(response)
                raise ValueError(f"Failed to fetch Typeform forms: {message}")

            payload = response.json()
            items = payload.get("items") or []
            if isinstance(items, list):
                forms.extend(item for item in items if isinstance(item, Mapping))

            page_count = payload.get("page_count")
            if not isinstance(page_count, int) or page >= page_count:
                break
            page += 1
        return forms

    def _fetch_form_title(
        self,
        *,
        form_id: str,
        token: str,
        token_type: str | None,
    ) -> str | None:
        response = self._api_request(
            method="GET",
            path=f"/forms/{form_id}",
            token=token,
            token_type=token_type,
        )
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError:  # pragma: no cover - defensive parsing
                payload = {}
            title = payload.get("title")
            return str(title) if isinstance(title, str) else None

        message = self._extract_error_message(response)
        raise SubscriptionError(
            f"Failed to access form '{form_id}': {message}",
            error_code="typeform_form_access_failed",
            external_response=self._safe_json(response),
        )

    def _upsert_webhook(
        self,
        *,
        form_id: str,
        webhook_tag: str,
        endpoint: str,
        secret: str,
        token: str,
        token_type: str | None,
    ) -> Mapping[str, Any]:
        payload = {
            "url": endpoint,
            "enabled": True,
            "secret": secret,
            "verify_ssl": True,
        }
        response = self._api_request(
            method="PUT",
            path=f"/forms/{form_id}/webhooks/{webhook_tag}",
            token=token,
            token_type=token_type,
            json=payload,
        )

        if response.status_code not in {200, 201}:
            message = self._extract_error_message(response)
            raise SubscriptionError(
                f"Failed to create Typeform webhook: {message}",
                error_code="typeform_webhook_creation_failed",
                external_response=response.json() if response.content else None,
            )

        if response.content:
            try:
                webhook_payload = response.json()
                if isinstance(webhook_payload, Mapping):
                    return webhook_payload
            except ValueError:  # pragma: no cover - defensive parsing
                pass
        return {}

    def _exchange_token(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = requests.post(
                self._OAUTH_TOKEN_URL,
                data=data,
                headers={"Accept": "application/json"},
                timeout=15,
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure guard
            raise TriggerProviderOAuthError(f"Failed to reach Typeform OAuth endpoint: {exc}") from exc

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise TriggerProviderOAuthError(f"Typeform OAuth error: {message}")

        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - defensive parsing
            raise TriggerProviderOAuthError(f"Invalid JSON response from Typeform OAuth: {exc}") from exc

    def _build_oauth_credentials(
        self,
        payload: Mapping[str, Any],
        *,
        fallback_refresh_token: str | None = None,
    ) -> TriggerOAuthCredentials:
        access_token = self._normalize_optional_string(payload.get("access_token"))
        if not access_token:
            raise TriggerProviderOAuthError("Typeform OAuth response missing access_token.")

        token_type = self._normalize_optional_string(payload.get("token_type")) or "Bearer"
        refresh_token = self._normalize_optional_string(payload.get("refresh_token")) or fallback_refresh_token

        expires_at = -1
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = int(time.time() + float(expires_in))
            expires_at = max(-1, expires_at - 60)

        credentials = {
            "access_token": access_token,
            "token_type": token_type,
        }
        if refresh_token:
            credentials["refresh_token"] = refresh_token
        scope = self._normalize_optional_string(payload.get("scope"))
        if scope:
            credentials["scope"] = scope

        return TriggerOAuthCredentials(credentials=credentials, expires_at=expires_at)

    def _api_request(
        self,
        *,
        method: str,
        path: str,
        token: str,
        expected_status: set[int] | None = None,
        token_type: str | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", self._build_authorization_header(token, token_type))
        headers.setdefault("Accept", "application/json")
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")

        response = requests.request(
            method,
            f"{self._API_BASE}{path}",
            headers=headers,
            timeout=15,
            **kwargs,
        )

        if expected_status and response.status_code not in expected_status:
            return response
        return response

    @staticmethod
    def _build_authorization_header(token: str, token_type: str | None) -> str:
        token = token.strip()
        if " " in token:
            return token
        scheme = token_type or "Bearer"
        return f"{scheme} {token}"

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, Mapping):
                description = payload.get("description") or payload.get("message")
                if description:
                    return str(description)
        except ValueError:
            pass
        text = response.text.strip()
        if text:
            return f"HTTP {response.status_code}: {text[:200]}"
        return f"HTTP {response.status_code}"

    @staticmethod
    def _safe_json(response: requests.Response) -> dict[str, Any] | None:
        if not response.content:
            return None
        try:
            data = response.json()
            return data if isinstance(data, dict) else None
        except ValueError:
            return None

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            if not value:
                return None
            value = value[0]
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return None

    @staticmethod
    def _get_required_token(credentials: Mapping[str, Any], credential_type: CredentialType) -> str:
        token = TypeformSubscriptionConstructor._normalize_optional_string(credentials.get("access_token"))
        if token:
            return token
        raise SubscriptionError(
            "Missing Typeform access token; connect using API Key or OAuth before creating this subscription.",
            error_code="typeform_missing_token",
        )

    @staticmethod
    def _get_token_for_validation(credentials: Mapping[str, Any]) -> str:
        token = TypeformSubscriptionConstructor._normalize_optional_string(credentials.get("access_token"))
        if not token:
            raise TriggerProviderCredentialValidationError("Access token is required for Typeform API calls.")
        return token

    @staticmethod
    def _get_token_type(credentials: Mapping[str, Any]) -> str | None:
        token_type = credentials.get("token_type")
        if isinstance(token_type, str):
            return token_type.strip()
        return None

    @staticmethod
    def _require_form_id(form_id: str | None) -> str:
        if not form_id:
            raise SubscriptionError("form_id is required when managing Typeform webhooks automatically.")
        return form_id

    @staticmethod
    def _generate_webhook_tag(form_id: str) -> str:
        unique = uuid.uuid4().hex[:10]
        return f"dify-{form_id[:8]}-{unique}"
