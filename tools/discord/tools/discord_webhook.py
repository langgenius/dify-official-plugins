import json
from typing import Any, Generator

import httpx
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


DISCORD_WEBHOOK_URL_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)
IS_COMPONENTS_V2 = 1 << 15
MAX_CONTENT_LENGTH = 2000
MAX_EMBEDS = 10


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}
    return bool(value)


def _parse_json_parameter(
    name: str, value: Any, expected_type: type
) -> tuple[Any, str | None]:
    if not _has_value(value):
        return None, None
    if isinstance(value, expected_type):
        return value, None
    if not isinstance(value, str):
        return None, f"Invalid parameter {name}: expected {expected_type.__name__} JSON"
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        return None, f"Invalid parameter {name}: malformed JSON ({e.msg})"
    if not isinstance(parsed, expected_type):
        return None, f"Invalid parameter {name}: expected {expected_type.__name__} JSON"
    return parsed, None


def _build_request(
    tool_parameters: dict[str, Any], default_username: str
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    content = tool_parameters.get("content") or ""
    if len(content) > MAX_CONTENT_LENGTH:
        return (
            {},
            {},
            f"Invalid parameter content: Discord messages must be at most {MAX_CONTENT_LENGTH} characters",
        )

    embeds, error = _parse_json_parameter("embeds_json", tool_parameters.get("embeds_json"), list)
    if error:
        return {}, {}, error
    if embeds is not None and len(embeds) > MAX_EMBEDS:
        return (
            {},
            {},
            f"Invalid parameter embeds_json: Discord supports at most {MAX_EMBEDS} embeds",
        )

    allowed_mentions, error = _parse_json_parameter(
        "allowed_mentions_json", tool_parameters.get("allowed_mentions_json"), dict
    )
    if error:
        return {}, {}, error

    components, error = _parse_json_parameter("components_json", tool_parameters.get("components_json"), list)
    if error:
        return {}, {}, error

    poll, error = _parse_json_parameter("poll_json", tool_parameters.get("poll_json"), dict)
    if error:
        return {}, {}, error

    applied_tags, error = _parse_json_parameter(
        "applied_tags_json", tool_parameters.get("applied_tags_json"), list
    )
    if error:
        return {}, {}, error

    if not any((content, embeds, components, poll)):
        return {}, {}, "Invalid message: provide at least one of content, embeds_json, components_json, or poll_json"

    flags = None
    if _has_value(tool_parameters.get("flags")):
        try:
            flags = int(tool_parameters["flags"])
        except (TypeError, ValueError):
            return {}, {}, "Invalid parameter flags: expected an integer"

    if flags is not None and flags & IS_COMPONENTS_V2 and any((content, embeds, poll)):
        return (
            {},
            {},
            "Invalid message: IS_COMPONENTS_V2 flags cannot be combined with content, embeds_json, or poll_json",
        )

    params: dict[str, Any] = {}
    if _has_value(tool_parameters.get("wait")):
        params["wait"] = str(_to_bool(tool_parameters["wait"])).lower()
    if _has_value(tool_parameters.get("thread_id")):
        params["thread_id"] = tool_parameters["thread_id"]
    if _has_value(tool_parameters.get("with_components")):
        params["with_components"] = str(_to_bool(tool_parameters["with_components"])).lower()

    payload: dict[str, Any] = {
        "username": tool_parameters.get("username") or default_username,
        "content": content,
        "avatar_url": tool_parameters.get("avatar_url") or None,
    }
    if _has_value(tool_parameters.get("tts")):
        payload["tts"] = _to_bool(tool_parameters["tts"])
    if embeds is not None:
        payload["embeds"] = embeds
    if allowed_mentions is not None:
        payload["allowed_mentions"] = allowed_mentions
    if components is not None:
        payload["components"] = components
    if flags is not None:
        payload["flags"] = flags
    if _has_value(tool_parameters.get("thread_name")):
        payload["thread_name"] = tool_parameters["thread_name"]
    if applied_tags is not None:
        payload["applied_tags"] = applied_tags
    if poll is not None:
        payload["poll"] = poll

    return params, payload, None


class DiscordWebhookTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Incoming Webhooks
        API Document:
            https://discord.com/developers/docs/resources/webhook#execute-webhook
        """
        webhook_url = tool_parameters.get("webhook_url", "")
        if not webhook_url.startswith(DISCORD_WEBHOOK_URL_PREFIXES):
            yield self.create_text_message(
                f"Invalid parameter webhook_url {webhook_url}, not a valid Discord webhook URL"
            )
            return

        default_username = getattr(self.runtime, "user_id", None) or "Dify"
        params, payload, error = _build_request(tool_parameters, default_username)
        if error:
            yield self.create_text_message(error)
            return

        headers = {"Content-Type": "application/json"}
        try:
            res = httpx.post(webhook_url, headers=headers, params=params, json=payload, timeout=20)
            if res.is_success:
                yield self.create_text_message("Discord webhook message sent successfully")
                if _to_bool(tool_parameters.get("wait")) and res.content:
                    yield self.create_json_message(res.json())
            else:
                yield self.create_text_message(
                    f"Failed to send Discord webhook message. status code: {res.status_code}, response: {res.text}"
                )
        except Exception as e:
            yield self.create_text_message(
                "Failed to send message through webhook. {}".format(e)
            )
