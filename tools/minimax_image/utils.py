from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

MODEL = "MiniMax-H3-Image"
TIMEOUT = (30, 610)
BASE_URLS = {
    "international": "https://api.minimax.io",
    "china": "https://api.minimaxi.com",
}


def base_url(credentials: dict[str, str]) -> str:
    return BASE_URLS.get(
        credentials.get("api_endpoint") or "international",
        BASE_URLS["international"],
    )


def headers(credentials: dict[str, str]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credentials['api_key']}",
        "Content-Type": "application/json",
    }


def emit_images(
    tool: Tool, credentials: dict[str, str], path: str, payload: dict[str, Any]
) -> Generator[ToolInvokeMessage, None, None]:
    try:
        response = requests.post(
            base_url(credentials) + path,
            json=payload,
            headers=headers(credentials),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        yield tool.create_text_message(f"Failed to call MiniMax Image API: {exc}")
        return

    try:
        body = response.json()
    except ValueError:
        yield tool.create_text_message(f"Got Error Response: {response.text}")
        return

    base_resp = body.get("base_resp") if isinstance(body, dict) else None
    if response.status_code != 200 or (
        isinstance(base_resp, dict) and base_resp.get("status_code") not in (0, None)
    ):
        message = None
        if isinstance(base_resp, dict):
            message = base_resp.get("status_msg")
        yield tool.create_text_message(f"Got Error Response: {message or response.text}")
        return

    images = body.get("data") or []
    yielded = False
    for item in images:
        url = item.get("url") if isinstance(item, dict) else None
        if url:
            yielded = True
            yield tool.create_image_message(url)
    if not yielded:
        yield tool.create_text_message("MiniMax returned no image data")
