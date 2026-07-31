"""Shared helper for calling the Slack Web API.

Every Slack Web API method lives at https://slack.com/api/<method> and is
authenticated with a Bearer token. Most write methods accept a JSON body;
read methods are called with GET query params. A few methods (Search, Stars,
updating your own profile) require a *user* token (xoxp-...) rather than a bot
token (xoxb-...), so the client can be told to require one.
"""

from typing import Any, Optional

import requests

SLACK_API_BASE = "https://slack.com/api/"


class SlackConfigError(Exception):
    """Raised when a required token is missing from the credentials."""


def _clean(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not payload:
        return payload
    return {k: v for k, v in payload.items() if v not in (None, "")}


class SlackClient:
    def __init__(self, credentials: dict[str, Any], require_user_token: bool = False):
        self.bot_token = (credentials.get("slack_bot_token") or "").strip()
        self.user_token = (credentials.get("slack_user_token") or "").strip()

        if require_user_token:
            if not self.user_token:
                raise SlackConfigError(
                    "This operation requires a Slack User Token (xoxp-...). "
                    "Add one under the plugin's 'Slack User Token' credential."
                )
            self.token = self.user_token
        else:
            if not self.bot_token:
                raise SlackConfigError("Slack Bot Token is required.")
            self.token = self.bot_token

    def call(
        self,
        method: str,
        http_method: str = "POST",
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        timeout: int = 60,
    ) -> requests.Response:
        url = SLACK_API_BASE + method
        headers = {"Authorization": f"Bearer {self.token}"}
        if http_method.upper() == "GET":
            return requests.get(
                url, headers=headers, params=_clean(params), timeout=timeout
            )
        headers["Content-Type"] = "application/json; charset=utf-8"
        return requests.post(
            url, headers=headers, json=_clean(json_body), timeout=timeout
        )
