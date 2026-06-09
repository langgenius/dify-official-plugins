"""Shared client + pure helpers for the Resemble Detect + Intelligence API.

This module has NO dependency on `dify_plugin`, so it can be exercised directly
by the live test harness in `tests/` — the plugin tools are thin wrappers around
the functions here, which means the tests cover the exact code path the plugin runs.

API contract (verified against docs.resemble.ai / resemble-mcp):
  Base:  https://app.resemble.ai/api/v2
  Auth:  Authorization: Bearer <RESEMBLE_API_KEY>
  Most jobs are async: submit, then poll the resource until `status` is terminal.
  Watermark endpoints support a synchronous `Prefer: wait` header.
"""
from __future__ import annotations

import time
from typing import Any, Iterator, Optional

import requests

DEFAULT_BASE_URL = "https://app.resemble.ai/api/v2"
TERMINAL_STATUSES = {"completed", "failed", "error", "cancelled", "success"}


class ResembleError(Exception):
    """API/transport error carrying a human-readable, user-facing message."""


# --------------------------------------------------------------------------- #
# Coercion helpers — tool parameters arrive as bool/number/str depending on UI.
# --------------------------------------------------------------------------- #
def to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# HTTP client
# --------------------------------------------------------------------------- #
class ResembleClient:
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        request_timeout: int = 60,
    ):
        if not api_key:
            raise ResembleError(
                "Missing Resemble API key. Add it in the plugin's provider credentials."
            )
        self.api_key = api_key.strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL
        self.request_timeout = request_timeout

    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        json_body: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> Any:
        try:
            resp = requests.request(
                method,
                self._url(path),
                json=json_body,
                headers=self._headers(extra_headers),
                timeout=(10, self.request_timeout),
            )
        except requests.RequestException as exc:
            raise ResembleError(f"Network error calling {method} {path}: {exc}") from exc

        if resp.status_code in (401, 403):
            raise ResembleError(
                "Authentication failed (HTTP {}). Check your Resemble API key.".format(
                    resp.status_code
                )
            )
        if resp.status_code == 429:
            raise ResembleError("Rate limited (HTTP 429). Back off and retry.")

        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        if resp.status_code >= 400:
            detail = _error_message(data) or f"HTTP {resp.status_code}"
            raise ResembleError(f"Resemble API error on {method} {path}: {detail}")
        return data

    def validate_key(self) -> None:
        """Cheap auth probe. Raises ResembleError ONLY on a clear auth failure,
        so a valid key is never rejected because of an unrelated 404/5xx."""
        try:
            resp = requests.get(
                self._url("/detect"), headers=self._headers(), timeout=(10, 20)
            )
        except requests.RequestException:
            return  # can't reach the API — don't claim the key is invalid
        if resp.status_code in (401, 403):
            raise ResembleError(
                "Authentication failed. Double-check your Resemble API key."
            )

    def poll(
        self,
        path: str,
        max_wait_seconds: int = 120,
    ) -> Any:
        """Poll GET <path> until `status` is terminal (or there is no status),
        or until the time budget runs out. Returns the last payload either way."""
        deadline = time.monotonic() + max(1, int(max_wait_seconds))
        delays = _backoff()
        last = self.request("GET", path)
        while True:
            status = _status_of(last)
            if status is None or status.lower() in TERMINAL_STATUSES:
                return last
            if time.monotonic() >= deadline:
                return last
            time.sleep(next(delays))
            last = self.request("GET", path)


def _backoff() -> Iterator[int]:
    for d in (2, 2, 3, 5, 5):
        yield d
    while True:
        yield 10


# --------------------------------------------------------------------------- #
# Response shape helpers (Resemble v2 commonly wraps payloads in {"item": {...}})
# --------------------------------------------------------------------------- #
def unwrap(data: Any) -> dict:
    if isinstance(data, dict) and isinstance(data.get("item"), dict):
        return data["item"]
    return data if isinstance(data, dict) else {}


def extract_uuid(data: Any) -> Optional[str]:
    d = unwrap(data)
    return d.get("uuid") or d.get("id")


def _status_of(data: Any) -> Optional[str]:
    d = unwrap(data)
    s = d.get("status")
    return s if isinstance(s, str) else None


def _error_message(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    for key in ("message", "error", "detail"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v
    errs = data.get("errors")
    if isinstance(errs, list) and errs:
        return "; ".join(str(x) for x in errs)
    if isinstance(errs, dict):
        return "; ".join(f"{k}: {v}" for k, v in errs.items())
    item = data.get("item")
    if isinstance(item, dict):
        return _error_message(item)
    return None


# --------------------------------------------------------------------------- #
# Pure request-body builders (shared by tools + tests)
# --------------------------------------------------------------------------- #
def build_detect_body(p: dict) -> dict:
    body: dict[str, Any] = {"url": (p.get("url") or "").strip()}
    for flag, api_key in (
        ("run_intelligence", "intelligence"),
        ("audio_source_tracing", "audio_source_tracing"),
        ("visualize", "visualize"),
        ("use_reverse_search", "use_reverse_search"),
        ("use_ood_detector", "use_ood_detector"),
        ("zero_retention_mode", "zero_retention_mode"),
    ):
        if to_bool(p.get(flag)):
            body[api_key] = True
    model_types = p.get("model_types")
    if model_types and model_types != "auto":
        body["model_types"] = model_types
    frame_length = to_int(p.get("frame_length"), None)
    if frame_length is not None:
        body["frame_length"] = frame_length
    for key in ("start_region", "end_region"):
        val = to_float(p.get(key), None)
        if val is not None:
            body[key] = val
    callback_url = (p.get("callback_url") or "").strip()
    if callback_url:
        body["callback_url"] = callback_url
    return body


def build_intelligence_body(p: dict) -> dict:
    body: dict[str, Any] = {}
    url = (p.get("url") or "").strip()
    token = (p.get("media_token") or "").strip()
    if url:
        body["url"] = url
    if token:
        body["media_token"] = token
    body["json"] = to_bool(p.get("structured_json"), default=True)
    media_type = p.get("media_type")
    if media_type and media_type != "auto":
        body["media_type"] = media_type
    detect_id = (p.get("detect_id") or "").strip()
    if detect_id:
        body["detect_id"] = detect_id
    callback_url = (p.get("callback_url") or "").strip()
    if callback_url:
        body["callback_url"] = callback_url
    return body


# --------------------------------------------------------------------------- #
# Human-readable summaries (the text message alongside the JSON message)
# --------------------------------------------------------------------------- #
def summarize_detection(result: Any) -> str:
    item = unwrap(result)
    status = item.get("status", "unknown")
    lines = [f"Detection status: {status}"]

    metrics = item.get("metrics") or {}
    if isinstance(metrics, dict) and metrics:
        lines.append(
            "Audio → label={} · aggregated_score={} · consistency={}".format(
                metrics.get("label"),
                metrics.get("aggregated_score"),
                metrics.get("consistency"),
            )
        )
    image = item.get("image_metrics") or {}
    if isinstance(image, dict) and image:
        lines.append(
            "Image → label={} · score={}".format(image.get("label"), image.get("score"))
        )
    video = item.get("video_metrics") or {}
    if isinstance(video, dict) and video:
        lines.append(
            "Video → label={} · score={} · certainty={}".format(
                video.get("label"), video.get("score"), video.get("certainty")
            )
        )
    tracing = item.get("audio_source_tracing") or {}
    if isinstance(tracing, dict) and tracing.get("label"):
        lines.append(f"Source tracing → {tracing.get('label')}")
    if item.get("intelligence"):
        lines.append("Intelligence → included (see JSON output).")

    if str(status).lower() not in ("completed", "failed"):
        lines.append("(Still processing — raise max_wait_seconds to wait longer.)")
    return "\n".join(lines)


def summarize_intelligence(result: Any) -> str:
    item = unwrap(result)
    fields = item.get("description") if isinstance(item.get("description"), dict) else item
    keys = [
        "transcription", "translation", "language", "emotion", "speaker_info",
        "message", "abnormalities", "misinformation", "scene_description",
    ]
    lines = ["Intelligence analysis:"]
    found = False
    for key in keys:
        if isinstance(fields, dict) and fields.get(key):
            found = True
            value = str(fields[key])
            if len(value) > 280:
                value = value[:277] + "..."
            lines.append(f"- {key}: {value}")
    if not found:
        lines.append("(See JSON output for the full structured result.)")
    return "\n".join(lines)


def summarize_watermark_apply(result: Any) -> str:
    item = unwrap(result)
    media = item.get("watermarked_media") or item.get("url")
    status = item.get("status", "completed")
    if media:
        return f"Watermark applied (status: {status}).\nWatermarked media: {media}"
    return f"Watermark apply status: {status} (see JSON output)."


def sanitize_output(data: Any, _max_inline: int = 200) -> Any:
    """Replace huge inline base64 `data:` URIs (e.g. ifl heatmaps) with a short
    placeholder so the JSON output stays readable and doesn't flood agent context.
    Real http(s) media URLs are preserved untouched."""
    if isinstance(data, dict):
        return {k: sanitize_output(v, _max_inline) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_output(v, _max_inline) for v in data]
    if isinstance(data, str) and data.startswith("data:") and len(data) > _max_inline:
        return f"<inline base64 omitted — {len(data)} chars>"
    return data


def watermark_error_hint(message: str) -> str:
    """Add a helpful note to the opaque 500 the API returns for unsupported
    watermark inputs (it works reliably for audio; some image/video URLs 500)."""
    if "internal error" in message.lower():
        return (
            message + " — watermarking works reliably for audio; some image/video "
            "inputs are not supported. Confirm the media is a public, reachable URL."
        )
    return message


def summarize_watermark_detect(result: Any) -> str:
    item = unwrap(result)
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    has = item.get("has_watermark")
    conf = item.get("confidence")
    if has is None:
        has = metrics.get("has_watermark")
        conf = metrics.get("confidence", conf)

    if isinstance(has, dict):
        # Audio: per-channel verdicts, e.g. {"channel_0": false, "channel_1": false}.
        found = any(bool(v) for v in has.values())
        detail = ", ".join(f"{k}={v}" for k, v in has.items())
        base = ("WATERMARK FOUND" if found else "no watermark detected") + f" (channels: {detail})"
    elif isinstance(has, bool):
        base = "WATERMARK FOUND" if has else "no watermark detected"
    else:
        return "Watermark detection complete (see JSON output)."
    if conf is not None:
        base += f" · confidence: {conf}"
    return base + "."
