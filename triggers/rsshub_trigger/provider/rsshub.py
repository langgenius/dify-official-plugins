from __future__ import annotations

from typing import Any, Mapping

from werkzeug import Request, Response

from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import TriggerDispatchError, TriggerValidationError
from dify_plugin.interfaces.trigger import Trigger


class RssHubTrigger(Trigger):
    """Handle RssHub webhook event dispatch with API Key verification."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        api_key = subscription.properties.get("api_key")
        if api_key:
            # Accept common places to carry the API key
            provided_key = self._extract_api_key(request)
            if not provided_key or provided_key != api_key:
                raise TriggerValidationError("Invalid or missing API key")
        # If no api_key configured, accept unauthenticated requests (user opted-in)

        payload = self._parse_payload(request)

        # Resolve event types via header/query/payload; may return multiple
        event_types = self._resolve_event_types(request, payload)
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        return EventDispatch(events=event_types, response=response)

    def _extract_api_key(self, request: Request) -> str | None:
        # Prefer explicit headers commonly used for webhooks
        for header in ("X-RssHub-Token", "X-RSSHub-Token", "X-Api-Key", "X-API-Key"):
            value = request.headers.get(header)
            if value:
                return value.strip()

        # Authorization Bearer
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            return auth.split(" ", 1)[1].strip()

        # Query params fallbacks (token, api_key)
        args = request.args
        for key in ("token", "api_key"):
            if args.get(key):
                return args.get(key)

        return None

    def _parse_payload(self, request: Request) -> Mapping[str, Any]:
        try:
            content_type = (request.headers.get("Content-Type") or "").lower()
            if "application/x-www-form-urlencoded" in content_type:
                # Some webhook senders post the JSON in a 'payload' form field
                form_data = request.form.get("payload")
                if not form_data:
                    raise TriggerDispatchError("Missing payload in form data")
                import json as _json

                payload = _json.loads(form_data)
            else:
                payload = request.get_json(force=True) or {}

            if not isinstance(payload, dict) or not payload:
                raise TriggerDispatchError("Empty or invalid JSON payload")
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging path
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc

    def _resolve_event_types(self, request: Request, payload: Mapping[str, Any]) -> list[str]:
        allowed = {"feed_update"}

        # 1) Explicit header
        for header in ("X-RssHub-Event", "X-Event-Type", "X-Webhook-Event"):
            v = request.headers.get(header)
            if v and v.strip().lower() in allowed:
                return [v.strip().lower()]

        # 2) Explicit query param
        for key in ("event", "type"):
            v = request.args.get(key)
            if v and v.strip().lower() in allowed:
                return [v.strip().lower()]

        # 3) Payload hint
        for key in ("event", "type"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip().lower() in allowed:
                return [v.strip().lower()]

        # 4) Heuristics
        # a) Feed update wrapper with items arrays
        data = payload.get("data") if isinstance(payload.get("data"), Mapping) else None
        if data is not None:
            # rss.app format: always feed_update
            return ["feed_update"]

        # Default
        return ["feed_update"]

    # No subscription constructor is needed; RssHub is configured to POST to the
    # endpoint externally, and we only validate with the API key stored in the
    # subscription's properties.
