"""Helpers shared by every Slack tool for parsing params and Slack responses."""

import json
from typing import Any, Optional

import requests


def parse_json_param(raw: Any) -> Optional[Any]:
    """Parse a JSON string parameter. Returns the value unchanged if it is
    already a dict/list, or None if empty. Raises ValueError on invalid JSON."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def slack_result(response: requests.Response) -> tuple[bool, dict, str]:
    """Interpret a Slack Web API response.

    Slack returns HTTP 200 with a JSON body containing an "ok" boolean; on
    failure the "error" field holds the reason. Returns (ok, data, error).
    """
    try:
        data = response.json()
    except ValueError:
        return (
            False,
            {},
            f"Non-JSON response (HTTP {response.status_code}): {response.text[:300]}",
        )
    if not isinstance(data, dict) or not data.get("ok"):
        error = ""
        if isinstance(data, dict):
            error = data.get("error") or ""
            if data.get("needed"):
                error += f" (needed scope: {data.get('needed')})"
        return False, (data if isinstance(data, dict) else {}), (
            error or f"Slack API returned ok=false (HTTP {response.status_code})"
        )
    return True, data, ""
