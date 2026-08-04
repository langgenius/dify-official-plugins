import json
from typing import Any, Optional

import httpx

SLACK_API_BASE = "https://slack.com/api"


class SlackApiError(Exception):
    """Raised when the Slack Web API returns an error or is unreachable."""

    def __init__(self, message: str, response: Optional[dict] = None):
        super().__init__(message)
        self.slack_error = message
        self.response = response


class SlackClient:
    """A thin wrapper around the Slack Web API using a Slack access token.

    Requests are sent as ``application/x-www-form-urlencoded`` with Bearer
    authentication. Form encoding (not JSON) is used deliberately: Slack ignores
    some parameters — notably ``types`` on ``conversations.list`` — when they are
    sent in a JSON body, which would silently drop private channels.
    """

    def __init__(self, token: str, timeout: float = 30.0):
        # Strip stray whitespace/newlines that often sneak in when pasting a token,
        # which would otherwise make an illegal Authorization header value.
        token = (token or "").strip()
        if not token:
            raise SlackApiError("A Slack access token is required.")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _encode(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Drop None values and render booleans as Slack expects ('true'/'false')."""
        body: dict[str, Any] = {}
        for key, value in (payload or {}).items():
            if value is None:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            body[key] = value
        return body

    def api_call(self, method: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Call a Slack Web API method (form-encoded) and return its JSON payload.

        Raises SlackApiError if the request fails or Slack responds with ok=false.
        """
        url = f"{SLACK_API_BASE}/{method}"
        try:
            resp = httpx.post(
                url, headers=self._headers(), data=self._encode(payload), timeout=self.timeout
            )
        except httpx.HTTPError as e:
            raise SlackApiError(f"HTTP error calling {method}: {e}")

        try:
            data = resp.json()
        except Exception:
            raise SlackApiError(f"Invalid response from Slack for {method}: {resp.text}")

        if not data.get("ok"):
            raise SlackApiError(data.get("error", "unknown_error"), response=data)
        return data

    def auth_test(self) -> dict[str, Any]:
        """Validate the token and return the authed identity (team, user, etc.)."""
        return self.api_call("auth.test")

    def list_channel_options(self, max_pages: int = 10) -> list[dict[str, str]]:
        """Return channels the token can access as [{'id','name'}].

        Public and private channels are queried separately and merged: Slack's
        ``conversations.list`` reliably returns private channels only when
        ``types`` is a single value, and drops them from a combined query.
        """
        seen: dict[str, str] = {}
        for channel_type in ("public_channel", "private_channel"):
            cursor: Optional[str] = None
            for _ in range(max_pages):
                resp = self.api_call(
                    "conversations.list",
                    {
                        "types": channel_type,
                        "limit": 200,
                        "cursor": cursor,
                        "exclude_archived": True,
                    },
                )
                for ch in resp.get("channels", []):
                    cid = ch.get("id")
                    if cid and cid not in seen:
                        seen[cid] = ch.get("name") or cid
                cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
                if not cursor:
                    break
        return [{"id": cid, "name": name} for cid, name in seen.items()]

    def upload_file(
        self,
        *,
        filename: str,
        data: bytes,
        title: Optional[str] = None,
        channel: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> dict[str, Any]:
        """Upload a file using Slack's modern external-upload flow.

        1. files.getUploadURLExternal to obtain a one-time upload URL and file id.
        2. POST the raw bytes to that URL.
        3. files.completeUploadExternal to finalize and optionally share to a channel.
        """
        # Step 1: request an upload URL.
        step1 = self.api_call(
            "files.getUploadURLExternal",
            {"filename": filename, "length": len(data)},
        )
        upload_url = step1.get("upload_url")
        file_id = step1.get("file_id")
        if not upload_url or not file_id:
            raise SlackApiError("Slack did not return an upload URL.", response=step1)

        # Step 2: upload the raw file bytes to the returned URL.
        try:
            up = httpx.post(
                upload_url,
                files={"file": (filename, data)},
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise SlackApiError(f"HTTP error uploading file bytes: {e}")
        if up.status_code != 200:
            raise SlackApiError(
                f"File byte upload failed with status {up.status_code}: {up.text}"
            )

        # Step 3: complete the upload and optionally share it.
        file_entry: dict[str, Any] = {"id": file_id}
        if title:
            file_entry["title"] = title
        return self.api_call(
            "files.completeUploadExternal",
            {
                "files": json.dumps([file_entry]),
                "channel_id": channel,
                "initial_comment": initial_comment,
            },
        )


class ChannelSelectMixin:
    """Mixin for Tools whose `channel` parameter is a dynamic-select.

    Implements `_fetch_parameter_options` so Dify can populate the dropdown with
    every channel (public and private) the configured access token can see.
    """

    def _fetch_parameter_options(self, parameter: str):
        from dify_plugin.entities import I18nObject, ParameterOption

        if parameter != "channel":
            return []
        token = (self.runtime.credentials or {}).get("access_token")
        if not token:
            raise ValueError("A Slack Access Token is required to list channels.")
        try:
            channels = SlackClient(token).list_channel_options()
        except SlackApiError as e:
            resp = e.response or {}
            detail = ""
            if resp.get("needed") is not None or resp.get("provided") is not None:
                detail = f" (needed: {resp.get('needed')}; provided: {resp.get('provided')})"
            raise ValueError(
                f"Could not list channels: {e.slack_error}{detail}. Ensure the token has "
                "the 'channels:read' and 'groups:read' scopes, then reinstall the app."
            )
        return [
            ParameterOption(value=c["id"], label=I18nObject(en_us=c["name"]))
            for c in channels
        ]
