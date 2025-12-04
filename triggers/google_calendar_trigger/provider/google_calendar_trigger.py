from __future__ import annotations

import datetime
import json
import secrets
import time
import urllib.parse
import uuid
from collections.abc import Callable, Mapping
from typing import Any

import requests
from werkzeug import Request, Response

from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.oauth import OAuthCredentials, TriggerOAuthCredentials
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerError,
    TriggerProviderCredentialValidationError,
    TriggerProviderOAuthError,
    TriggerValidationError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor

_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


class SyncTokenExpiredError(TriggerError):
    """Raised when Google Calendar reports an invalidated sync token."""

    pass


def _encode_calendar_id(calendar_id: str) -> str:
    return urllib.parse.quote(calendar_id, safe="@._-")


def _isoformat_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_google_error(resp: requests.Response) -> str:
    try:
        data = resp.json()
        error = data.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if message:
                return str(message)
        if isinstance(data, Mapping):
            message = data.get("message")
            if message:
                return str(message)
    except Exception:
        pass

    return resp.text or f"HTTP {resp.status_code}"


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _retrieve_sync_token(
    access_token: str,
    calendar_id: str,
    error_factory: Callable[[str], Exception],
) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{_CALENDAR_API_BASE}/calendars/{_encode_calendar_id(calendar_id)}/events"
    params: dict[str, str] = {"showDeleted": "true", "singleEvents": "true", "maxResults": "50"}

    next_sync_token: str | None = None

    while True:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
        except requests.RequestException as exc:
            raise error_factory(f"Network error while obtaining sync token: {exc}") from exc

        if resp.status_code != 200:
            raise error_factory(f"Failed to obtain calendar sync token: {_parse_google_error(resp)}")

        data: dict[str, Any] = resp.json() or {}
        next_page = data.get("nextPageToken")
        next_sync = data.get("nextSyncToken")

        if next_page:
            params["pageToken"] = next_page
            continue

        if isinstance(next_sync, str) and next_sync:
            next_sync_token = next_sync
        break

    if not next_sync_token:
        raise error_factory(
            "Google Calendar response missing nextSyncToken after paginating all events. "
            "See https://developers.google.com/calendar/api/guides/sync for requirements."
        )
    return next_sync_token


def _parse_rfc3339(value: Any) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(text)
    except Exception:
        return None


def _is_recent_creation(event: Mapping[str, Any], threshold_seconds: int = 1) -> bool:
    seq = event.get("sequence")
    seq_value: int | None = None
    if isinstance(seq, int):
        seq_value = seq
    elif isinstance(seq, str):
        try:
            seq_value = int(seq)
        except ValueError:
            seq_value = None
    seq_looks_new = seq_value is None or seq_value <= 1

    created_dt = _parse_rfc3339(event.get("created"))
    updated_dt = _parse_rfc3339(event.get("updated"))
    if created_dt and updated_dt:
        time_gap = abs((updated_dt - created_dt).total_seconds())
        time_looks_new = time_gap <= threshold_seconds
    else:
        time_looks_new = True

    return bool(seq_looks_new and time_looks_new)


class GoogleCalendarTrigger(Trigger):
    """Dispatch Google Calendar push notifications into concrete event families."""

    _CAL_BASE = _CALENDAR_API_BASE
    _MAX_SEEN_EVENT_IDS = 500

    # ---------------- Trigger dispatch lifecycle -----------------
    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        properties = subscription.properties or {}
        parameters = subscription.parameters or {}

        expected_channel_id: str | None = properties.get("channel_id")
        expected_token: str | None = properties.get("channel_token")
        channel_id = (request.headers.get("X-Goog-Channel-ID") or "").strip()
        channel_token = (request.headers.get("X-Goog-Channel-Token") or "").strip()
        if expected_channel_id and channel_id != expected_channel_id:
            raise TriggerValidationError("Channel ID mismatch for Google Calendar notification")
        if expected_token and channel_token != expected_token:
            raise TriggerValidationError("Channel token verification failed")

        resource_state = (request.headers.get("X-Goog-Resource-State") or "").strip().lower()
        resource_id = (request.headers.get("X-Goog-Resource-ID") or "").strip()
        calendar_id = properties.get("calendar_id") or parameters.get("calendar_id") or "primary"
        calendar_id = str(calendar_id)
        include_cancelled = _to_bool(parameters.get("include_cancelled"), True)

        access_token: str | None = (self.runtime.credentials or {}).get("access_token") if self.runtime else None
        if not access_token:
            return EventDispatch(events=[], response=self._value_error("Missing access token for Google Calendar API"))

        if not self.runtime:
            raise TriggerDispatchError("Runtime context unavailable")
        session = self.runtime.session

        subscription_key = properties.get("subscription_key") or ""
        sync_storage_key = f"gcal:{subscription_key}:sync_token"

        # Ensure we have a sync token persisted for incremental fetches
        sync_token: str | None = None
        initialized_now = False
        if session.storage.exist(sync_storage_key):
            sync_token = session.storage.get(sync_storage_key).decode("utf-8")
        else:
            initial_sync = properties.get("initial_sync_token")
            if initial_sync:
                sync_token = str(initial_sync)
                session.storage.set(sync_storage_key, sync_token.encode("utf-8"))
            else:
                sync_token = self._bootstrap_sync_token(access_token=access_token, calendar_id=calendar_id)
                session.storage.set(sync_storage_key, sync_token.encode("utf-8"))
                initialized_now = True

        if initialized_now:
            # No events to emit on initial bootstrap
            return EventDispatch(events=[], response=self._ok())

        # The first webhook after a watch is created has resourceState=sync; nothing to process.
        if resource_state == "sync":
            return EventDispatch(events=[], response=self._ok())

        try:
            items, next_sync_token = self._fetch_events_delta(
                access_token=access_token,
                calendar_id=calendar_id,
                sync_token=sync_token,
            )
        except SyncTokenExpiredError:
            fresh_token = self._bootstrap_sync_token(access_token=access_token, calendar_id=calendar_id)
            if fresh_token:
                session.storage.set(sync_storage_key, fresh_token.encode("utf-8"))
            return EventDispatch(events=[], response=self._ok())

        if next_sync_token:
            session.storage.set(sync_storage_key, next_sync_token.encode("utf-8"))

        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        deleted: list[dict[str, Any]] = []

        for raw in items:
            if not isinstance(raw, Mapping):
                continue
            event = dict(raw)
            status = (event.get("status") or "").lower()
            change_type: str
            if status == "cancelled":
                change_type = "deleted"
            elif _is_recent_creation(event):
                change_type = "created"
            else:
                change_type = "updated"

            event["changeType"] = change_type

            if change_type == "deleted":
                if include_cancelled:
                    deleted.append(event)
                continue
            if change_type == "created":
                created.append(event)
            else:
                updated.append(event)

        events: list[str] = []
        if created:
            events.append("google_calendar_event_created")
        if updated:
            events.append("google_calendar_event_updated")
        if deleted:
            events.append("google_calendar_event_deleted")

        payload = {
            "calendarId": calendar_id,
            "resourceState": resource_state,
            "resourceId": resource_id,
            "channelId": channel_id,
            "events": items,
            "created": created,
            "updated": updated,
            "deleted": deleted,
        }
        if next_sync_token:
            payload["nextSyncToken"] = next_sync_token
        if include_cancelled:
            payload["includeCancelled"] = True

        return EventDispatch(events=events, response=self._ok(), payload=payload)

    # ---------------- HTTP helpers -----------------
    def _value_error(self, message: str) -> Response:
        return Response(
            response=json.dumps({"status": "value_error", "message": message}),
            status=400,
            mimetype="application/json",
        )

    def _ok(self) -> Response:
        return Response(response=json.dumps({"status": "ok"}), status=200, mimetype="application/json")

    def _fetch_events_delta(
        self,
        access_token: str,
        calendar_id: str,
        sync_token: str,
    ) -> tuple[list[dict[str, Any]], str]:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self._CAL_BASE}/calendars/{_encode_calendar_id(calendar_id)}/events"
        params: dict[str, str] = {
            "syncToken": sync_token,
            "showDeleted": "true",
            "singleEvents": "true",
        }

        items: list[dict[str, Any]] = []
        next_sync_token: str | None = None

        while True:
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
            except requests.RequestException as exc:
                raise TriggerDispatchError(f"Network error while fetching calendar delta: {exc}") from exc

            if resp.status_code == 410:
                raise SyncTokenExpiredError()
            if resp.status_code != 200:
                raise TriggerDispatchError(f"Failed to fetch calendar delta: {_parse_google_error(resp)}")

            data: dict[str, Any] = resp.json() or {}
            batch = data.get("items") or []
            if isinstance(batch, list):
                for it in batch:
                    if isinstance(it, Mapping):
                        items.append(dict(it))

            next_page = data.get("nextPageToken")
            next_sync = data.get("nextSyncToken")
            if next_page:
                params["pageToken"] = next_page
            else:
                if isinstance(next_sync, str) and next_sync:
                    next_sync_token = next_sync
                break

        return items, next_sync_token or sync_token

    def _bootstrap_sync_token(self, access_token: str, calendar_id: str) -> str:
        return _retrieve_sync_token(access_token, calendar_id, lambda msg: TriggerDispatchError(msg))


class GoogleCalendarSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Google Calendar trigger subscription lifecycle."""

    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _CAL_BASE = _CALENDAR_API_BASE

    _DEFAULT_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

    # ---------------- Credential handling -----------------
    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        raise TriggerProviderCredentialValidationError(
            "Google Calendar trigger does not support API Key credentials. Please use OAuth authorization."
        )

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._DEFAULT_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        request: Request,
    ) -> TriggerOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("No authorization code provided")

        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise TriggerProviderOAuthError("Client ID and Client Secret are required")

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            resp = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise TriggerProviderOAuthError(f"Network error during OAuth token exchange: {exc}") from exc

        if resp.status_code != 200:
            raise TriggerProviderOAuthError(f"OAuth token exchange failed: {_parse_google_error(resp)}")

        payload: dict[str, Any] = resp.json() or {}
        access_token: str | None = payload.get("access_token")
        if not access_token:
            raise TriggerProviderOAuthError("Google OAuth response missing access_token")

        expires_in: int = int(payload.get("expires_in") or 0)
        expires_at: int = int(time.time()) + expires_in if expires_in else -1

        credentials: dict[str, Any] = {"access_token": access_token}
        refresh_token = payload.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token:
            credentials["refresh_token"] = refresh_token

        # Best-effort fetch of account email for display/help
        try:
            headers_info = {"Authorization": f"Bearer {access_token}"}
            info_resp = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers=headers_info, timeout=10)
            if info_resp.status_code == 200:
                info_payload = info_resp.json() or {}
                email = info_payload.get("email")
                if isinstance(email, str) and email:
                    credentials["account_email"] = email
        except requests.RequestException:
            pass

        return TriggerOAuthCredentials(credentials=credentials, expires_at=expires_at)

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> OAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("Missing refresh_token for OAuth refresh")

        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        if not client_id or not client_secret:
            raise TriggerProviderOAuthError("Client ID and Client Secret are required for refresh")

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            resp = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise TriggerProviderOAuthError(f"Network error during OAuth refresh: {exc}") from exc

        if resp.status_code != 200:
            raise TriggerProviderOAuthError(f"OAuth refresh failed: {_parse_google_error(resp)}")

        payload: dict[str, Any] = resp.json() or {}
        access_token: str | None = payload.get("access_token")
        if not access_token:
            raise TriggerProviderOAuthError("Google OAuth refresh response missing access_token")

        expires_in: int = int(payload.get("expires_in") or 0)
        expires_at: int = int(time.time()) + expires_in if expires_in else -1

        refreshed: dict[str, Any] = {"access_token": access_token, "refresh_token": refresh_token}
        if credentials.get("account_email"):
            refreshed["account_email"] = credentials["account_email"]

        return OAuthCredentials(credentials=refreshed, expires_at=expires_at)

    # ---------------- Subscription management -----------------
    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        access_token = credentials.get("access_token")
        if not access_token:
            raise SubscriptionError("Missing access_token for Google Calendar API", error_code="MISSING_CREDENTIALS")

        calendar_id = parameters.get("calendar_id") or "primary"
        calendar_id = str(calendar_id)

        channel_id = str(uuid.uuid4())
        channel_token = secrets.token_urlsafe(32)
        subscription_key = uuid.uuid4().hex

        body = {
            "id": channel_id,
            "type": "webhook",
            "address": endpoint,
            "token": channel_token,
        }
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        url = f"{self._CAL_BASE}/calendars/{_encode_calendar_id(calendar_id)}/events/watch"
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                f"Network error while creating calendar watch: {exc}", error_code="NETWORK_ERROR"
            ) from exc

        if resp.status_code not in (200, 201):
            raise SubscriptionError(
                f"Failed to create calendar watch: {_parse_google_error(resp)}",
                error_code="WATCH_CREATION_FAILED",
            )

        data: dict[str, Any] = resp.json() or {}
        resource_id = data.get("resourceId")
        expiration_ms = data.get("expiration")
        if not resource_id:
            raise SubscriptionError("Google Calendar response missing resourceId", error_code="WATCH_CREATION_FAILED")

        expires_at = int(time.time()) + 24 * 60 * 60
        if isinstance(expiration_ms, (int, float)):
            expires_at = int(expiration_ms / 1000)

        initial_sync_token = self._bootstrap_sync_token(access_token=access_token, calendar_id=calendar_id)

        params = dict(parameters)
        if "calendar_id" not in params:
            params["calendar_id"] = calendar_id
        if "include_cancelled" not in params:
            params["include_cancelled"] = True
        if "enrich_event_details" not in params:
            params["enrich_event_details"] = True

        properties: dict[str, Any] = {
            "calendar_id": calendar_id,
            "channel_id": channel_id,
            "channel_token": channel_token,
            "resource_id": resource_id,
            "subscription_key": subscription_key,
            "initial_sync_token": initial_sync_token,
        }
        if data.get("resourceUri"):
            properties["resource_uri"] = data["resourceUri"]

        return Subscription(
            expires_at=expires_at,
            endpoint=endpoint,
            parameters=params,
            properties=properties,
        )

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        access_token = credentials.get("access_token")
        if not access_token:
            raise SubscriptionError("Missing access_token for Google Calendar API", error_code="MISSING_CREDENTIALS")

        properties = dict(subscription.properties or {})
        calendar_id = properties.get("calendar_id") or subscription.parameters.get("calendar_id") or "primary"
        calendar_id = str(calendar_id)

        # Stop existing channel if we have identifiers
        self._stop_channel(access_token=access_token, properties=properties)

        channel_id = str(uuid.uuid4())
        channel_token = secrets.token_urlsafe(32)

        body = {
            "id": channel_id,
            "type": "webhook",
            "address": subscription.endpoint,
            "token": channel_token,
        }
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        url = f"{self._CAL_BASE}/calendars/{_encode_calendar_id(calendar_id)}/events/watch"
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                f"Network error while refreshing calendar watch: {exc}", error_code="NETWORK_ERROR"
            ) from exc

        if resp.status_code not in (200, 201):
            raise SubscriptionError(
                f"Failed to refresh calendar watch: {_parse_google_error(resp)}",
                error_code="WATCH_REFRESH_FAILED",
            )

        data: dict[str, Any] = resp.json() or {}
        resource_id = data.get("resourceId")
        expiration_ms = data.get("expiration")
        if not resource_id:
            raise SubscriptionError(
                "Google Calendar refresh response missing resourceId", error_code="WATCH_REFRESH_FAILED"
            )

        expires_at = int(time.time()) + 24 * 60 * 60
        if isinstance(expiration_ms, (int, float)):
            expires_at = int(expiration_ms / 1000)

        initial_sync_token = self._bootstrap_sync_token(access_token=access_token, calendar_id=calendar_id)

        params = dict(subscription.parameters or {})
        params["calendar_id"] = calendar_id
        if "include_cancelled" not in params:
            params["include_cancelled"] = True
        if "enrich_event_details" not in params:
            params["enrich_event_details"] = True

        properties.update(
            {
                "calendar_id": calendar_id,
                "channel_id": channel_id,
                "channel_token": channel_token,
                "resource_id": resource_id,
                "initial_sync_token": initial_sync_token,
            }
        )
        if data.get("resourceUri"):
            properties["resource_uri"] = data["resourceUri"]

        return Subscription(
            expires_at=expires_at,
            endpoint=subscription.endpoint,
            parameters=params,
            properties=properties,
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        access_token = credentials.get("access_token")
        if not access_token:
            return UnsubscribeResult(success=False, message="Missing access_token for Google Calendar API")

        properties = subscription.properties or {}
        success = self._stop_channel(access_token=access_token, properties=properties)
        if not success:
            return UnsubscribeResult(success=False, message="Failed to stop Google Calendar channel")
        return UnsubscribeResult(success=True, message="Google Calendar channel stopped")

    def _stop_channel(self, access_token: str, properties: Mapping[str, Any]) -> bool:
        channel_id = properties.get("channel_id")
        resource_id = properties.get("resource_id")
        if not channel_id or not resource_id:
            return False

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body = {"id": channel_id, "resourceId": resource_id}
        try:
            resp = requests.post(f"{self._CAL_BASE}/channels/stop", headers=headers, json=body, timeout=10)
        except requests.RequestException:
            return False

        return resp.status_code in (200, 204)

    def _bootstrap_sync_token(self, access_token: str, calendar_id: str) -> str:
        return _retrieve_sync_token(
            access_token,
            calendar_id,
            lambda msg: SubscriptionError(msg, error_code="SYNC_TOKEN_ERROR"),
        )

    def _fetch_parameter_options(
        self,
        parameter: str,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> list[ParameterOption]:
        if parameter != "calendar_id":
            return []

        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("access_token is required to list calendars")

        headers = {"Authorization": f"Bearer {access_token}"}
        params: dict[str, str] = {"minAccessRole": "reader"}
        url = f"{self._CAL_BASE}/users/me/calendarList"

        options: list[ParameterOption] = []
        while True:
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
            except requests.RequestException as exc:
                raise ValueError(f"Network error while listing calendars: {exc}") from exc

            if resp.status_code != 200:
                raise ValueError(f"Failed to list calendars: {_parse_google_error(resp)}")

            data: dict[str, Any] = resp.json() or {}
            items = data.get("items") or []
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, Mapping):
                        continue
                    calendar_id = it.get("id")
                    summary = it.get("summary") or calendar_id
                    if calendar_id:
                        options.append(ParameterOption(value=str(calendar_id), label=I18nObject(en_US=str(summary))))

            page_token = data.get("nextPageToken")
            if page_token:
                params["pageToken"] = page_token
            else:
                break

        if not any(opt.value == "primary" for opt in options):
            options.insert(0, ParameterOption(value="primary", label=I18nObject(en_US="Primary Calendar")))
        return options
