import base64
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

API_URL = "https://aistudio.baidu.com/llm/lmapi/v3/images/generations"
DEFAULT_MODEL = "ernie-image-turbo"
DEFAULT_SIZE = "1024x1024"


def _build_payload(params: dict[str, Any]) -> dict[str, Any]:
    prompt = (params.get("prompt") or "").strip()
    if not prompt:
        raise InvokeError("Prompt is required")

    n = int(params.get("n") or 1)
    if not 1 <= n <= 4:
        raise InvokeError("n must be between 1 and 4")

    payload: dict[str, Any] = {
        "model": params.get("model") or DEFAULT_MODEL,
        "prompt": prompt,
        "n": n,
        "size": params.get("size") or DEFAULT_SIZE,
        "watermark": bool(params.get("watermark", False)),
    }
    seed = params.get("seed")
    if seed not in (None, ""):
        payload["seed"] = int(seed)
    return payload


def _fetch_image(url: str) -> bytes:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


class ErnieImageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = (self.runtime.credentials or {}).get("access_token")
        if not token:
            raise InvokeError("Access token is missing")

        payload = _build_payload(tool_parameters)

        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
        except requests.RequestException as exc:
            raise InvokeError(f"Network error: {exc}") from exc

        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {}
        if resp.status_code != 200 or "data" not in body:
            msg = body.get("errorMsg") or body.get("detail") or resp.text
            raise InvokeError(f"ERNIE Image request failed (HTTP {resp.status_code}): {msg}")

        items = body.get("data") or []
        if not items:
            raise InvokeError("ERNIE Image returned no data")

        for index, item in enumerate(items):
            blob = self._image_blob(item)
            if blob is None:
                continue
            yield self.create_blob_message(
                blob=blob,
                meta={
                    "mime_type": "image/png",
                    "filename": f"ernie_image_{index + 1}.png",
                },
            )

        yield self.create_json_message(
            {
                "model": payload["model"],
                "size": payload["size"],
                "n": payload["n"],
                "trace_id": body.get("trace_id"),
                "data": [
                    {"url": item.get("url"), "revised_prompt": item.get("revised_prompt")}
                    for item in items
                ],
            }
        )

    @staticmethod
    def _image_blob(item: dict[str, Any]) -> bytes | None:
        try:
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"])
            if item.get("url"):
                return _fetch_image(item["url"])
        except Exception:
            return None
        return None
