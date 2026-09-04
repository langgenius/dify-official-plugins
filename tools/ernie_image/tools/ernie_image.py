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
MAX_PROMPT_LENGTH = 2048
SUPPORTED_MODELS = frozenset({"ernie-image", "ernie-image-turbo"})
OFFICIAL_SIZES = frozenset(
    {
        "1024x1024",
        "848x1264",
        "768x1376",
        "896x1200",
        "1264x848",
        "1376x768",
        "1200x896",
    }
)
# Keep existing workflows working while new configurations use the current official size list.
LEGACY_SIZES = frozenset({"1024x768", "768x1024", "1280x720", "720x1280", "1792x1024", "1024x1792"})
SUPPORTED_SIZES = OFFICIAL_SIZES | LEGACY_SIZES


def _parse_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise InvokeError(f"{name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvokeError(f"{name} must be an integer") from exc


def _build_payload(params: dict[str, Any]) -> dict[str, Any]:
    prompt = (params.get("prompt") or "").strip()
    if not prompt:
        raise InvokeError("Prompt is required")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise InvokeError(f"Prompt must not exceed {MAX_PROMPT_LENGTH} characters")

    model = params.get("model") or DEFAULT_MODEL
    if model not in SUPPORTED_MODELS:
        raise InvokeError(f"Unsupported model: {model}")

    size = params.get("size") or DEFAULT_SIZE
    if size not in SUPPORTED_SIZES:
        raise InvokeError(f"Unsupported size: {size}")

    raw_n = params.get("n")
    if raw_n is None or raw_n == "":
        raw_n = 1
    n = _parse_integer(raw_n, "n")
    if not 1 <= n <= 4:
        raise InvokeError("n must be between 1 and 4")

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "watermark": bool(params.get("watermark", False)),
    }
    seed = params.get("seed")
    if seed not in (None, ""):
        payload["seed"] = _parse_integer(seed, "seed")
    return payload


def _fetch_image(url: str) -> bytes:
    resp = requests.get(url, timeout=(10, 120))
    resp.raise_for_status()
    return resp.content


def _error_message(body: Any, fallback: str) -> str:
    if not isinstance(body, dict):
        return fallback
    for key in ("errorMsg", "message", "detail"):
        if body.get(key):
            return str(body[key])
    error = body.get("error")
    if isinstance(error, dict):
        return _error_message(error, fallback)
    if error:
        return str(error)
    return fallback


class ErnieImageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = (self.runtime.credentials or {}).get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise InvokeError("Access token is missing")
        token = token.strip()

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
        items = body.get("data") if isinstance(body, dict) else None
        if not resp.ok or not isinstance(items, list):
            msg = _error_message(body, resp.text)
            raise InvokeError(f"ERNIE Image request failed (HTTP {resp.status_code}): {msg}")

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
                "id": body.get("id"),
                "created": body.get("created"),
                "trace_id": body.get("trace_id"),
                "data": [
                    {"url": item.get("url"), "revised_prompt": item.get("revised_prompt")}
                    for item in items
                ],
            }
        )

    @staticmethod
    def _image_blob(item: dict[str, Any]) -> bytes | None:
        if not isinstance(item, dict):
            return None
        try:
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"])
            if item.get("url"):
                return _fetch_image(item["url"])
        except (TypeError, ValueError, requests.RequestException):
            return None
        return None
