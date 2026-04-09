from __future__ import annotations

import base64
import json
import secrets
import time
import urllib.parse
from collections.abc import Mapping
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
    TriggerProviderCredentialValidationError,
    TriggerProviderOAuthError,
    TriggerValidationError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class GmailTrigger(Trigger):
    """Handle Gmail Pub/Sub push event dispatch.

    Responsibilities:
    - Optionally verify Pub/Sub OIDC JWT
    - Parse Pub/Sub envelope and Gmail notification
    - Fetch Gmail history delta since last checkpoint
    - Split delta into concrete event families and stash batches
    - Return EventDispatch with events and a combined payload for convenience
    """

    _GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        props = subscription.properties or {}
        # 1) Verify Pub/Sub OIDC if enabled
        self._maybe_verify_pubsub_oidc(request, props, subscription.endpoint)

        # 2) Parse Gmail push notification from Pub/Sub envelope
        notification = self._parse_pubsub_push(request)

        # 3) Build auth headers using runtime OAuth credentials
        access_token = (self.runtime.credentials or {}).get("access_token") if self.runtime else None
        if not access_token:
            return EventDispatch(events=[], response=self._value_error("Missing access token for Gmail API"))
        headers = {"Authorization": f"Bearer {access_token}"}
        user_id: str = "me"

        # 4) Prepare storage keys and checkpoint
        sub_key = props.get("subscription_key") or ""
        checkpoint_key = f"gmail:{sub_key}:history_checkpoint"
        # storage keys kept for backward compatibility in events fallback; we no longer write pending batches

        session = self.runtime.session
        if not session.storage.exist(checkpoint_key):
            # First notification: initialize checkpoint and return 200
            session.storage.set(checkpoint_key, str(notification["historyId"]).encode("utf-8"))
            return EventDispatch(events=[], response=self._ok())

        start_history_id: str = session.storage.get(checkpoint_key).decode("utf-8")

        # 5) Fetch history delta since last checkpoint
        messages, added, deleted, labels_added, labels_removed = self._fetch_history_delta(
            headers=headers,
            user_id=user_id,
            start_history_id=start_history_id,
        )

        # Always advance checkpoint to current notification's historyId
        session.storage.set(checkpoint_key, str(notification["historyId"]).encode("utf-8"))

        # 6) Build combined payload and select events (no storage stashing)
        events: list[str] = []
        if added:
            events.append("gmail_message_added")
        if deleted:
            events.append("gmail_message_deleted")
        if labels_added:
            events.append("gmail_label_added")
        if labels_removed:
            events.append("gmail_label_removed")
        combined_payload = {
            "historyId": str(notification["historyId"]),
            "messages": messages,
            "message_added": added,
            "message_deleted": deleted,
            "label_added": labels_added,
            "label_removed": labels_removed,
        }

        return EventDispatch(events=events, response=self._ok(), payload=combined_payload)

    # ---------------- Helper methods (trigger) -----------------
    def _value_error(self, message: str) -> Response:
        return Response(
            response=json.dumps({"status": "value_error", "message": message}), status=400, mimetype="application/json"
        )

    def _ok(self) -> Response:
        return Response(response=json.dumps({"status": "ok"}), status=200, mimetype="application/json")

    def _maybe_verify_pubsub_oidc(self, request: Request, props: Mapping[str, Any], endpoint: str) -> None:
        require_oidc = bool(props.get("require_oidc"))
        if not require_oidc:
            return
        token = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if not token:
            raise TriggerValidationError("Missing OIDC bearer token for Pub/Sub push")
        audience = props.get("oidc_audience") or endpoint
        expected_sa = props.get("oidc_service_account_email")
        self._verify_oidc_token(token=token, audience=audience, expected_email=expected_sa)

    def _parse_pubsub_push(self, request: Request) -> dict[str, Any]:
        try:
            envelope: Mapping[str, Any] = request.get_json(force=True)
        except Exception as exc:
            raise TriggerDispatchError(f"Invalid JSON: {exc}") from exc
        if "message" not in envelope:
            raise TriggerDispatchError("Missing Pub/Sub message")
        data_b64: str | None = (envelope.get("message") or {}).get("data")
        if not data_b64:
            raise TriggerDispatchError("Missing Pub/Sub message.data")
        try:
            decoded = base64.b64decode(data_b64).decode("utf-8")
            notification = json.loads(decoded)
        except Exception as exc:
            raise TriggerDispatchError(f"Invalid Pub/Sub data: {exc}") from exc
        if not notification.get("historyId") or not notification.get("emailAddress"):
            raise TriggerDispatchError("Missing historyId or emailAddress in Gmail notification")
        return notification

    def _fetch_history_delta(
        self,
        headers: Mapping[str, str],
        user_id: str,
        start_history_id: str,
    ):
        """Fetch Gmail history delta and return categorized changes.

        If the start_history_id is invalid/out-of-date, reset the pointer and return empty changes.
        """
        added: list[dict[str, Any]] = []
        deleted: list[dict[str, Any]] = []
        labels_added: list[dict[str, Any]] = []
        labels_removed: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []

        url = f"{self._GMAIL_BASE}/users/{user_id}/history"
        params: dict[str, Any] = {"startHistoryId": start_history_id}

        while True:
            resp: requests.Response = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                # history id may be invalid/out of range; swallow this batch and move checkpoint forward by caller
                return [], [], [], [], []
            data: dict[str, Any] = resp.json() or {}
            for h in data.get("history", []) or []:
                for item in h.get("messagesAdded", []) or []:
                    msg = item.get("message") or {}
                    if not msg.get("id"):
                        continue
                    added.append({"id": msg.get("id"), "threadId": msg.get("threadId")})
                for item in h.get("messagesDeleted", []) or []:
                    msg = item.get("message") or {}
                    if msg.get("id"):
                        deleted.append({"id": msg.get("id"), "threadId": msg.get("threadId")})
                for item in h.get("labelsAdded", []) or []:
                    msg = item.get("message") or {}
                    if msg.get("id"):
                        labels_added.append(
                            {
                                "id": msg.get("id"),
                                "threadId": msg.get("threadId"),
                                "labelIds": item.get("labelIds") or [],
                            }
                        )
                for item in h.get("labelsRemoved", []) or []:
                    msg = item.get("message") or {}
                    if msg.get("id"):
                        labels_removed.append(
                            {
                                "id": msg.get("id"),
                                "threadId": msg.get("threadId"),
                                "labelIds": item.get("labelIds") or [],
                            }
                        )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            params["pageToken"] = page_token

        messages.extend(added + deleted)
        return messages, added, deleted, labels_added, labels_removed

    def _verify_oidc_token(self, token: str, audience: str, expected_email: str | None = None) -> None:
        """Verify OIDC token from Pub/Sub push using google-auth if available."""
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            req = google_requests.Request()
            claims = id_token.verify_oauth2_token(token, req, audience=audience)
            issuer = claims.get("iss")
            if issuer not in ("https://accounts.google.com", "accounts.google.com"):
                raise TriggerValidationError("Invalid OIDC token issuer")
            if expected_email and claims.get("email") != expected_email:
                raise TriggerValidationError("OIDC token service account email mismatch")
        except ImportError as exc:
            raise TriggerValidationError("google-auth is required for OIDC verification but not installed") from exc
        except Exception as exc:  # pragma: no cover - verification failure
            raise TriggerValidationError(f"OIDC verification failed: {exc}") from exc


class GmailSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Gmail trigger subscriptions (watch/stop/refresh, OAuth)."""

    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"

    _DEFAULT_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
    _SUBSCRIPTION_PREFIX = "dify-gmail-"

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        """Gmail trigger does not support API Key credentials.

        Raise a friendly validation error to guide users to OAuth.
        """
        raise TriggerProviderCredentialValidationError(
            "Gmail trigger does not support API Key credentials. Please use OAuth authorization."
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
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> TriggerOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("No code provided")

        if not system_credentials.get("client_id") or not system_credentials.get("client_secret"):
            raise TriggerProviderOAuthError("Client ID or Client Secret is required")

        # 1. Exchange authorization code for OAuth tokens
        data: dict[str, str] = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp: requests.Response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)
        payload: dict[str, Any] = resp.json()
        access_token: str | None = payload.get("access_token")
        if not access_token:
            raise TriggerProviderOAuthError(f"Error in Google OAuth: {payload}")

        expires_in: int = int(payload.get("expires_in") or 0)
        refresh_token: str | None = payload.get("refresh_token")
        expires_at: int = int(time.time()) + expires_in if expires_in else -1

        # 2. Parse and store GCP configuration from system_credentials
        import json as _json

        credentials: dict[str, str] = {"access_token": access_token}
        if refresh_token:
            credentials["refresh_token"] = refresh_token

        # Extract GCP info and store in credentials for later use (required)
        gcp_sa = (system_credentials.get("gcp_service_account_json") or "").strip()
        if not gcp_sa:
            raise TriggerProviderOAuthError("GCP Service Account JSON is required")

        try:
            sa_info = _json.loads(gcp_sa)
            gcp_project_id = sa_info.get("project_id")
            if not gcp_project_id:
                raise TriggerProviderOAuthError("GCP Service Account JSON must contain 'project_id' field")

            # Store GCP configuration in credentials (Pub/Sub will be created in create_subscription)
            credentials["gcp_project_id"] = gcp_project_id
            credentials["gcp_service_account_json"] = gcp_sa
            # Determine Gmail account email so that we can assign a stable Pub/Sub topic.
            headers_profile = {"Authorization": f"Bearer {access_token}"}
            prof_resp = requests.get(f"{self._GMAIL_BASE}/users/me/profile", headers=headers_profile, timeout=10)
            if prof_resp.status_code != 200:
                try:
                    prof_payload: dict[str, Any] = prof_resp.json()
                except Exception:
                    prof_payload = {"message": prof_resp.text}
                raise TriggerProviderOAuthError(f"Failed to fetch Gmail profile: {prof_payload}")

            email_addr = (prof_resp.json() or {}).get("emailAddress") or ""
            if not email_addr:
                raise TriggerProviderOAuthError("Gmail profile response missing 'emailAddress'")
            credentials["gmail_email"] = email_addr

            import hashlib as _hashlib

            topic_id = f"dify-gmail-{_hashlib.sha1(email_addr.lower().encode()).hexdigest()[:16]}"
            credentials["gcp_topic_id"] = topic_id

            try:
                topic_path = self._ensure_topic(project_id=gcp_project_id, sa_info=sa_info, topic_id=topic_id)
                credentials["gcp_topic_path"] = topic_path
            except Exception as exc:
                raise TriggerProviderOAuthError(f"Failed to provision Pub/Sub topic: {exc}") from exc
        except _json.JSONDecodeError as exc:
            raise TriggerProviderOAuthError("Invalid GCP Service Account JSON format") from exc

        return TriggerOAuthCredentials(credentials=credentials, expires_at=expires_at)

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> OAuthCredentials:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("Missing refresh_token for OAuth refresh")

        data: dict[str, str] = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp: requests.Response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)
        payload: dict[str, Any] = resp.json()
        access_token: str | None = payload.get("access_token")
        if not access_token:
            raise TriggerProviderOAuthError(f"OAuth refresh failed: {payload}")

        expires_in: int = int(payload.get("expires_in") or 0)
        expires_at: int = int(time.time()) + expires_in if expires_in else -1
        refreshed: dict[str, str] = {"access_token": access_token}
        if refresh_token:
            refreshed["refresh_token"] = refresh_token

        # Preserve GCP configuration from existing credentials
        if credentials.get("gcp_project_id"):
            refreshed["gcp_project_id"] = credentials["gcp_project_id"]
        if credentials.get("gcp_service_account_json"):
            refreshed["gcp_service_account_json"] = credentials["gcp_service_account_json"]
        if credentials.get("gmail_email"):
            refreshed["gmail_email"] = credentials["gmail_email"]
        if credentials.get("gcp_topic_id"):
            refreshed["gcp_topic_id"] = credentials["gcp_topic_id"]
        if credentials.get("gcp_topic_path"):
            refreshed["gcp_topic_path"] = credentials["gcp_topic_path"]

        return OAuthCredentials(credentials=refreshed, expires_at=expires_at)

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        # Always watch the authenticated user (me)
        import hashlib as _hashlib
        import uuid as _uuid

        # 0) Basic inputs and validation
        subscription_key = _uuid.uuid4().hex
        gcp_project_id = credentials.get("gcp_project_id")
        gcp_sa = credentials.get("gcp_service_account_json")
        access_token: str | None = credentials.get("access_token")
        if not gcp_project_id or not gcp_sa:
            raise SubscriptionError(
                "GCP configuration not found in credentials. Please re-authorize OAuth.",
                error_code="MISSING_GCP_CREDENTIALS",
            )
        if not access_token:
            raise SubscriptionError("Missing access_token for Gmail API")

        # 1) Resolve Gmail email and build a stable topic per email
        email_addr: str = credentials.get("gmail_email") or ""
        if not email_addr:
            headers_at = {"Authorization": f"Bearer {access_token}"}
            prof = requests.get(f"{self._GMAIL_BASE}/users/me/profile", headers=headers_at, timeout=10)
            if prof.status_code != 200:
                try:
                    err = prof.json()
                except Exception:
                    err = {"message": prof.text}
                raise SubscriptionError(
                    f"Failed to get Gmail profile: {err}", error_code="PROFILE_FETCH_FAILED", external_response=err
                )
            email_addr = (prof.json() or {}).get("emailAddress") or ""
            if not email_addr:
                raise SubscriptionError("No emailAddress in Gmail profile", error_code="PROFILE_FETCH_FAILED")

        topic_id = credentials.get("gcp_topic_id")
        if not topic_id:
            topic_id = f"dify-gmail-{_hashlib.sha1(email_addr.lower().encode()).hexdigest()[:16]}"

        # 2) Ensure Pub/Sub Topic and per-subscription Push Subscription
        require_oidc: bool = bool(parameters.get("require_oidc") or False)
        oidc_audience: str = parameters.get("oidc_audience") or endpoint

        # Derive a unique push subscription name for this subscription (endpoint +   key)
        push_sub_name = f"dify-gmail-{_hashlib.sha1(endpoint.encode()).hexdigest()[:16]}-{subscription_key[:8]}"
        info = self._ensure_pubsub(
            project_id=gcp_project_id,
            sa_json=gcp_sa,
            endpoint=endpoint,
            topic_id=topic_id,
            push_subscription_name=push_sub_name,
            require_oidc=require_oidc,
            audience=oidc_audience,
        )
        topic_name = info["topic_path"]

        # 3) Issue users.watch pointing to the shared email topic (no labelIds here)
        headers: dict[str, str] = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body: dict[str, Any] = {"topicName": topic_name}
        url = f"{self._GMAIL_BASE}/users/me/watch"
        try:
            resp: requests.Response = requests.post(url, headers=headers, json=body, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                f"Network error while calling users.watch: {exc}", error_code="NETWORK_ERROR"
            ) from exc
        if resp.status_code not in (200, 201):
            try:
                err: dict[str, Any] = resp.json()
            except Exception:
                err = {"message": resp.text}
            raise SubscriptionError(
                f"Failed to create Gmail watch: {err}",
                error_code="WATCH_CREATION_FAILED",
                external_response=err if isinstance(err, dict) else None,
            )

        data: dict[str, Any] = resp.json() or {}
        expiration_ms: int = int(data.get("expiration") or 0)
        # Gmail watch is time-limited; if expiration is not provided, use 6 days as a safe default
        expires_at: int = int(expiration_ms / 1000) if expiration_ms else int(time.time()) + 6 * 24 * 60 * 60

        # 4) Persist properties for later operations
        label_ids: list[str] = parameters.get("label_ids") or []
        properties: dict[str, Any] = {
            "gmail_email": email_addr,
            "topic_name": topic_name,
            "topic_id": topic_id,
            "push_subscription_name": push_sub_name,
            "label_ids": label_ids,  # used for event-side filtering
            "require_oidc": require_oidc,
            "oidc_audience": oidc_audience,
            "subscription_key": subscription_key,
        }
        if parameters.get("oidc_service_account_email"):
            properties["oidc_service_account_email"] = parameters.get("oidc_service_account_email")

        return Subscription(
            expires_at=expires_at,
            endpoint=endpoint,
            parameters=parameters,
            properties=properties,
        )

    def _ensure_topic(self, project_id: str, sa_info: Mapping[str, Any], topic_id: str) -> str:
        """Ensure the shared Pub/Sub topic exists and Gmail can publish to it."""
        from google.api_core.exceptions import AlreadyExists, Forbidden, PermissionDenied
        from google.cloud import pubsub_v1
        from google.iam.v1 import policy_pb2
        from google.oauth2 import service_account as _sa

        creds = _sa.Credentials.from_service_account_info(sa_info)
        publisher = pubsub_v1.PublisherClient(credentials=creds)
        topic_path = publisher.topic_path(project_id, topic_id)
        try:
            publisher.create_topic(name=topic_path)
        except AlreadyExists:
            pass
        except (Forbidden, PermissionDenied) as exc:  # pragma: no cover - permission errors
            raise TriggerProviderOAuthError(
                "Service account lacks Pub/Sub permission to create topic. "
                "Grant roles/pubsub.admin (or equivalent) and retry."
            ) from exc

        try:
            policy = publisher.get_iam_policy(request={"resource": topic_path})
        except (Forbidden, PermissionDenied) as exc:  # pragma: no cover - permission errors
            raise TriggerProviderOAuthError(
                "Service account lacks permission to read topic IAM policy. "
                "Ensure roles/pubsub.admin (or equivalent) is granted."
            ) from exc
        member = "serviceAccount:gmail-api-push@system.gserviceaccount.com"
        role = "roles/pubsub.publisher"
        if not any(b.role == role and member in b.members for b in policy.bindings):
            policy.bindings.append(policy_pb2.Binding(role=role, members=[member]))
            try:
                publisher.set_iam_policy(request={"resource": topic_path, "policy": policy})
            except (Forbidden, PermissionDenied) as exc:  # pragma: no cover - permission errors
                raise TriggerProviderOAuthError(
                    "Service account lacks permission to update topic IAM policy. "
                    "Grant roles/pubsub.admin (or equivalent) and retry."
                ) from exc

        return topic_path

    # Minimal auto Pub/Sub helper using google-cloud-pubsub
    def _ensure_pubsub(
        self,
        project_id: str,
        sa_json: str,
        endpoint: str,
        topic_id: str,
        push_subscription_name: str,
        require_oidc: bool,
        audience: str,
    ) -> dict[str, str]:
        import json as _json

        from google.api_core.exceptions import AlreadyExists, NotFound
        from google.cloud import pubsub_v1
        from google.oauth2 import service_account as _sa

        info = _json.loads(sa_json) if isinstance(sa_json, str) else sa_json
        topic_path = self._ensure_topic(project_id=project_id, sa_info=info, topic_id=topic_id)

        creds = _sa.Credentials.from_service_account_info(info)
        sa_email = info.get("client_email")

        subscriber = pubsub_v1.SubscriberClient(credentials=creds)

        # Ensure a dedicated push subscription per Dify subscription (endpoint + subscription key)
        sub_id = push_subscription_name
        sub_path = subscriber.subscription_path(project_id, sub_id)
        push = pubsub_v1.types.PushConfig(push_endpoint=endpoint)
        if require_oidc and sa_email:
            push.oidc_token.service_account_email = sa_email
            push.oidc_token.audience = audience
        try:
            subscriber.create_subscription(name=sub_path, topic=topic_path, push_config=push)
        except AlreadyExists:
            # Verify existing subscription config; if mismatched, recreate
            sub = subscriber.get_subscription(subscription=sub_path)
            need_recreate = False
            if sub.topic != topic_path:
                need_recreate = True
            else:
                # Compare push config
                cur_push = sub.push_config
                cur_endpoint = cur_push.push_endpoint
                cur_sa = getattr(cur_push.oidc_token, "service_account_email", None)
                cur_aud = getattr(cur_push.oidc_token, "audience", None)
                if cur_endpoint != endpoint:
                    need_recreate = True
                if require_oidc and (cur_sa != sa_email or cur_aud != audience):
                    need_recreate = True
            if need_recreate:
                try:
                    subscriber.delete_subscription(subscription=sub_path)
                except NotFound:
                    pass
                subscriber.create_subscription(name=sub_path, topic=topic_path, push_config=push)

        return {"topic_path": topic_path}

    def _delete_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> UnsubscribeResult:
        # Only delete the dedicated Push Subscription; do not stop the global Gmail watch by default
        gcp_project_id = credentials.get("gcp_project_id")
        gcp_sa = credentials.get("gcp_service_account_json")
        if not gcp_project_id or not gcp_sa:
            return UnsubscribeResult(success=False, message="Missing GCP credentials for cleanup")

        props = subscription.properties or {}
        push_name: str | None = props.get("push_subscription_name")
        topic_id: str | None = props.get("topic_id")
        if not push_name:
            return UnsubscribeResult(success=False, message="Missing push subscription name for cleanup")

        try:
            self._delete_managed_resources(
                project_id=gcp_project_id, sa_json=gcp_sa, topic_name=topic_id or "", subscription_name=push_name
            )
        except Exception as exc:
            return UnsubscribeResult(success=False, message=f"Cleanup failed: {exc}")

        # Best-effort cleanup: if no plugin-managed subscriptions remain on the topic,
        # and the topic has no subscriptions at all, stop Gmail watch and delete topic.
        try:
            cleanup_msg = self._best_effort_cleanup(
                project_id=gcp_project_id,
                sa_json=gcp_sa,
                topic_id=topic_id,
                access_token=credentials.get("access_token"),
            )
            msg = f"Push subscription deleted. {cleanup_msg}" if cleanup_msg else "Push subscription deleted"
            return UnsubscribeResult(success=True, message=msg)
        except Exception:
            # Swallow cleanup errors to avoid blocking unsubscribe
            return UnsubscribeResult(success=True, message="Push subscription deleted")

    def _delete_managed_resources(self, project_id: str, sa_json: str, topic_name: str, subscription_name: str) -> None:
        """Delete dedicated Push Subscription; topic deletion is skipped by default for safety."""
        import json as _json

        from google.api_core.exceptions import NotFound
        from google.cloud import pubsub_v1
        from google.oauth2 import service_account as _sa

        info = _json.loads(sa_json) if isinstance(sa_json, str) else sa_json
        creds = _sa.Credentials.from_service_account_info(info)

        # Delete Push Subscription
        subscriber = pubsub_v1.SubscriberClient(credentials=creds)
        sub_path = subscriber.subscription_path(project_id, subscription_name)
        try:
            subscriber.delete_subscription(subscription=sub_path)
        except NotFound:
            pass
        # Optionally delete topic when no managed subscriptions remain (skipped to avoid disrupting others)

    def _best_effort_cleanup(
        self,
        project_id: str,
        sa_json: str,
        topic_id: str | None,
        access_token: str | None,
    ) -> str:
        """If no subscriptions remain on the topic, stop watch and delete the topic.

        Returns a short message describing the action taken, or empty string if no action.
        """
        if not topic_id:
            return ""

        import json as _json

        from google.api_core.exceptions import NotFound
        from google.cloud import pubsub_v1
        from google.oauth2 import service_account as _sa

        info = _json.loads(sa_json) if isinstance(sa_json, str) else sa_json
        creds = _sa.Credentials.from_service_account_info(info)

        publisher = pubsub_v1.PublisherClient(credentials=creds)
        topic_path = publisher.topic_path(project_id, topic_id)

        # List all subscriptions on the topic
        subs_iter = publisher.list_topic_subscriptions(request={"topic": topic_path})
        subs = [s for s in subs_iter]
        if not subs:
            # No subscriptions at all -> safe to stop watch and delete topic
            stopped = False
            if access_token:
                try:
                    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                    url = f"{self._GMAIL_BASE}/users/me/stop"
                    requests.post(url, headers=headers, json={}, timeout=10)
                    stopped = True
                except Exception:
                    stopped = False
            try:
                publisher.delete_topic(topic=topic_path)
                return "Watch stopped and topic deleted" if stopped else "Topic deleted"
            except NotFound:
                return ""
        # If there are remaining subscriptions, especially non-plugin ones, do nothing
        return ""

    def _refresh_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> Subscription:
        # Re-issue users.watch with previous topic
        access_token = credentials.get("access_token")
        if not access_token:
            raise SubscriptionError("Missing access_token for Gmail API", error_code="MISSING_CREDENTIALS")

        topic_name: str | None = (subscription.properties or {}).get("topic_name")

        if not topic_name:
            raise SubscriptionError("Missing topic_name in subscription properties", error_code="INVALID_PROPERTIES")

        headers: dict[str, str] = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body: dict[str, Any] = {"topicName": topic_name}

        url = f"{self._GMAIL_BASE}/users/me/watch"
        resp: requests.Response = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code not in (200, 201):
            try:
                err: dict[str, Any] = resp.json()
            except Exception:
                err = {"message": resp.text}
            raise SubscriptionError(
                f"Failed to refresh Gmail watch: {err}", error_code="WATCH_REFRESH_FAILED", external_response=err
            )

        data: dict[str, Any] = resp.json() or {}
        expiration_ms: int | None = data.get("expiration")
        expires_at: int = int(expiration_ms / 1000) if expiration_ms else int(time.time()) + 6 * 24 * 60 * 60

        properties: dict[str, Any] = dict(subscription.properties or {})

        return Subscription(
            expires_at=expires_at,
            endpoint=subscription.endpoint,
            properties=properties,
        )

    def _fetch_parameter_options(
        self, parameter: str, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> list[ParameterOption]:
        if parameter != "label_ids":
            return []

        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("access_token is required to fetch labels")

        # List labels for the authenticated user
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{self._GMAIL_BASE}/users/me/labels"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            try:
                err = resp.json()
                msg = err.get("error", {}).get("message", str(err))
            except Exception:
                msg = resp.text
            raise ValueError(f"Failed to fetch Gmail labels: {msg}")

        labels = resp.json().get("labels", []) or []
        options: list[ParameterOption] = []
        for lab in labels:
            lid = lab.get("id")
            name = lab.get("name") or lid
            if lid:
                options.append(ParameterOption(value=lid, label=I18nObject(en_US=name)))
        return options
