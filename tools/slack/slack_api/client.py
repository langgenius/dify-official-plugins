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
    """A thin wrapper around the Slack Web API using a Bot User OAuth Token.

    All standard methods are called via POST with a JSON body and Bearer
    authentication, which Slack supports for the chat.*, conversations.*,
    reactions.* and users.* families used by this plugin.
    """

    def __init__(self, token: str, timeout: float = 30.0):
        if not token:
            raise SlackApiError("A Slack Bot User OAuth Token is required.")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def api_call(self, method: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Call a Slack Web API method and return its parsed JSON payload.

        Raises SlackApiError if the request fails or Slack responds with ok=false.
        """
        # Drop None values so optional parameters are simply omitted.
        body = {k: v for k, v in (payload or {}).items() if v is not None}
        url = f"{SLACK_API_BASE}/{method}"
        try:
            resp = httpx.post(url, headers=self._headers(), json=body, timeout=self.timeout)
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

    def _form_call(self, method: str, data: dict[str, Any]) -> dict[str, Any]:
        """Call a Slack Web API method with a form-encoded body (Bearer auth)."""
        body = {k: v for k, v in data.items() if v is not None}
        url = f"{SLACK_API_BASE}/{method}"
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                data=body,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise SlackApiError(f"HTTP error calling {method}: {e}")
        try:
            payload = resp.json()
        except Exception:
            raise SlackApiError(f"Invalid response from Slack for {method}: {resp.text}")
        if not payload.get("ok"):
            raise SlackApiError(payload.get("error", "unknown_error"), response=payload)
        return payload

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
        step1 = self._form_call(
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
        return self._form_call(
            "files.completeUploadExternal",
            {
                "files": json.dumps([file_entry]),
                "channel_id": channel,
                "initial_comment": initial_comment,
            },
        )
