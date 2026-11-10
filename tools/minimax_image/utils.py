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
    """POST one MiniMax image request and yield the returned images.

    API, transport, parsing and empty-result failures raise instead of yielding text: a text
    result would let Dify mark the invocation successful even though no image was produced,
    which bypasses workflow retries and error branches. MiniMax is not idempotent, so nothing
    here retries the POST - a failed request has to be re-issued deliberately.
    """
    try:
        response = requests.post(
            base_url(credentials) + path,
            json=payload,
            headers=headers(credentials),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ValueError(f"Failed to call MiniMax Image API: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ValueError(f"Got Error Response: {response.text}") from exc

    base_resp = body.get("base_resp") if isinstance(body, dict) else None
    if response.status_code != 200 or (
        isinstance(base_resp, dict) and base_resp.get("status_code") not in (0, None)
    ):
        message = None
        if isinstance(base_resp, dict):
            message = base_resp.get("status_msg")
        raise ValueError(f"Got Error Response: {message or response.text}")

    images = body.get("data") or []
    yielded = False
    for item in images:
        url = item.get("url") if isinstance(item, dict) else None
        if url:
            yielded = True
            yield tool.create_image_message(url)
    if not yielded:
        raise ValueError("MiniMax returned no image data")
