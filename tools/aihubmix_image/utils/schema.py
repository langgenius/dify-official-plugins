"""Endpoint discovery and schema-driven request building.

The gateway describes every model it serves at
``GET /call/schema/models/{model}/endpoints``: which paths accept it, whether the call is
synchronous, and a JSON Schema for the request body. The unified image endpoint declares
``additionalProperties: false``, so a field the model does not declare is rejected with
HTTP 400 rather than ignored (``mai-image-2.6-flash`` rejects ``n``, for example). Building
the payload from the live schema instead of hard-coded per-model tables is what keeps the
plugin correct as the catalog moves.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from utils.client import AIHubMixClient, GatewayError

# The unified AIHubMix task endpoint (POST /ai/v1/images/generations). The same document
# also lists the OpenAI-compatible passthroughs, which this plugin deliberately skips.
UNIFIED_KIND = "image"

SCHEMA_CACHE_TTL = 600
_SCHEMA_CACHE: dict[tuple[str, str], tuple[float, "ImageEndpoint"]] = {}


@dataclass(frozen=True)
class ImageEndpoint:
    model: str
    display_name: str
    path: str
    method: str
    mode: str
    poll_path: str
    poll_method: str
    status_values: tuple[str, ...]
    schema: dict[str, Any]

    @property
    def properties(self) -> dict[str, Any]:
        properties = self.schema.get("properties")
        return properties if isinstance(properties, dict) else {}

    @property
    def required(self) -> tuple[str, ...]:
        required = self.schema.get("required")
        return tuple(required) if isinstance(required, list) else ()

    def declares(self, name: str) -> bool:
        return name in self.properties

    def media_fields(self) -> tuple[str, ...]:
        return tuple(name for name, prop in self.properties.items() if _is_media_ref(prop))


def _is_media_ref(prop: Any) -> bool:
    return isinstance(prop, dict) and bool(prop.get("x-media-ref"))


def fetch_image_endpoint(client: AIHubMixClient, model: str) -> ImageEndpoint:
    """Fetch (and cache) the unified image endpoint document for ``model``."""
    model = (model or "").strip()
    if not model:
        raise GatewayError("Model is required")

    key = (client.base_url, model)
    cached = _SCHEMA_CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < SCHEMA_CACHE_TTL:
        return cached[1]

    try:
        document = client.get_json(
            f"/call/schema/models/{model}/endpoints",
            authenticated=False,
        )
    except GatewayError as exc:
        if exc.status == 404:
            raise GatewayError(
                f"Model '{model}' is not served by the unified image endpoint "
                f"(/ai/v1/images/generations). Pick a model from the dropdown, which lists "
                f"only models the gateway currently serves."
            ) from exc
        raise

    endpoint = _select_unified_endpoint(document, model)
    _SCHEMA_CACHE[key] = (now, endpoint)
    return endpoint


def _select_unified_endpoint(document: Any, model: str) -> ImageEndpoint:
    endpoints = document.get("endpoints") if isinstance(document, dict) else None
    if not isinstance(endpoints, list):
        raise GatewayError(f"Endpoint discovery returned no endpoints for '{model}'")

    chosen = next((item for item in endpoints if isinstance(item, dict) and item.get("kind") == UNIFIED_KIND), None)
    if chosen is None:
        kinds = ", ".join(sorted({str(item.get("kind")) for item in endpoints if isinstance(item, dict)}))
        raise GatewayError(
            f"Model '{model}' exposes no unified image endpoint (kinds: {kinds or 'none'})"
        )

    lifecycle = chosen.get("lifecycle") if isinstance(chosen.get("lifecycle"), dict) else {}
    request = chosen.get("request") if isinstance(chosen.get("request"), dict) else {}
    schema = request.get("schema") if isinstance(request.get("schema"), dict) else {}
    status_values = lifecycle.get("status_values")

    return ImageEndpoint(
        model=str(document.get("model") or model),
        display_name=str(document.get("display_name") or document.get("model") or model),
        path=str(chosen.get("path") or "/ai/v1/images/generations"),
        method=str(chosen.get("method") or "POST").upper(),
        mode=str(lifecycle.get("mode") or "sync"),
        poll_path=str(lifecycle.get("poll_path") or ""),
        poll_method=str(lifecycle.get("poll_method") or "GET").upper(),
        status_values=tuple(str(value) for value in status_values) if isinstance(status_values, list) else (),
        schema=schema,
    )


# --------------------------------------------------------------------------------------
# JSON Schema subset used by the media endpoints: type / enum / const / anyOf / oneOf /
# minimum / maximum / pattern. Validating locally turns a gateway 400 into a message that
# names the values this model actually accepts.
# --------------------------------------------------------------------------------------


def _alternatives(prop: dict[str, Any]) -> list[dict[str, Any]]:
    """The anyOf/oneOf arms of a property, which is where the media schemas put the detail."""
    alternatives: list[dict[str, Any]] = []
    for key in ("anyOf", "oneOf"):
        for branch in prop.get(key) or []:
            if isinstance(branch, dict):
                alternatives.append(branch)
    return alternatives


def _branches(prop: dict[str, Any]) -> list[dict[str, Any]]:
    return [prop, *_alternatives(prop)]


def allowed_values(prop: dict[str, Any]) -> list[Any]:
    """Enumerated values, whether spelled ``enum`` or as ``const`` branches."""
    values: list[Any] = []
    for branch in _branches(prop):
        for value in branch.get("enum") or []:
            if value is not None and value not in values:
                values.append(value)
        const = branch.get("const")
        if const is not None and const not in values:
            values.append(const)
    # An alternative that carries a free-form type (string with a pattern, integer, ...) means
    # the field is not a closed enum, so the consts are examples rather than the whole domain.
    # The property's own "type" does not count: it sits alongside anyOf as a type hint.
    has_open_branch = any(
        branch.get("type") and not branch.get("enum") and branch.get("const") is None
        for branch in _alternatives(prop)
    )
    return [] if has_open_branch and not prop.get("enum") else values


def _patterns(prop: dict[str, Any]) -> list[str]:
    return [str(branch["pattern"]) for branch in _branches(prop) if branch.get("pattern")]


def _consts(prop: dict[str, Any]) -> list[Any]:
    return [branch["const"] for branch in _branches(prop) if branch.get("const") is not None]


def _bound(prop: dict[str, Any], key: str) -> float | None:
    for branch in _branches(prop):
        value = branch.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _types(prop: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for branch in _branches(prop):
        declared = branch.get("type")
        if isinstance(declared, str):
            types.add(declared)
        elif isinstance(declared, list):
            types.update(str(item) for item in declared)
    types.discard("null")
    return types


def coerce_and_validate(name: str, prop: dict[str, Any], value: Any) -> Any:
    """Coerce a Dify parameter to the schema's type and check it against the constraints."""
    types = _types(prop)

    if types & {"integer", "number"} and isinstance(value, str):
        try:
            value = int(value) if "integer" in types else float(value)
        except ValueError:
            raise GatewayError(f"Parameter '{name}' must be a number, got '{value}'") from None
    if "integer" in types and isinstance(value, float) and value.is_integer():
        value = int(value)
    if types == {"boolean"} and isinstance(value, str):
        value = value.strip().lower() in {"true", "1", "yes"}

    enum = allowed_values(prop)
    if enum and value not in enum:
        rendered = ", ".join(str(item) for item in enum)
        raise GatewayError(f"Parameter '{name}' must be one of: {rendered} (got '{value}')")

    patterns = _patterns(prop)
    if patterns and isinstance(value, str) and value not in _consts(prop):
        if not any(re.fullmatch(pattern, value) for pattern in patterns):
            raise GatewayError(
                f"Parameter '{name}' has an invalid format: '{value}' "
                f"(expected {' or '.join(patterns)})"
            )

    minimum, maximum = _bound(prop, "minimum"), _bound(prop, "maximum")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if minimum is not None and value < minimum:
            raise GatewayError(f"Parameter '{name}' must be >= {minimum} (got {value})")
        if maximum is not None and value > maximum:
            raise GatewayError(f"Parameter '{name}' must be <= {maximum} (got {value})")

    return value


def parse_extra(raw: Any) -> dict[str, Any]:
    """Parse the vendor passthrough escape hatch (a JSON object typed into the tool form)."""
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise GatewayError(f"'extra' must be valid JSON: {exc}") from None
    if not isinstance(parsed, dict):
        raise GatewayError("'extra' must be a JSON object, e.g. {\"background\": \"transparent\"}")
    return parsed


def build_payload(
    endpoint: ImageEndpoint,
    *,
    prompt: str,
    scalars: dict[str, Any],
    media: dict[str, Any],
    extra: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Build the request body, dropping anything this model does not declare.

    Returns the payload plus human-readable notes about what was dropped, so the caller can
    surface them instead of silently changing what the user asked for.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise GatewayError("Prompt is required")

    payload: dict[str, Any] = {"model": endpoint.model, "prompt": prompt}
    notes: list[str] = []

    # size and aspect_ratio are mutually exclusive upstream; prefer the more specific one.
    if scalars.get("size") not in (None, "") and scalars.get("aspect_ratio") not in (None, ""):
        scalars = dict(scalars)
        scalars.pop("aspect_ratio")
        notes.append("'aspect_ratio' ignored because 'size' was set (they are mutually exclusive)")

    for name, value in scalars.items():
        if value in (None, ""):
            continue
        prop = endpoint.properties.get(name)
        if not isinstance(prop, dict):
            notes.append(f"'{name}' ignored: not supported by {endpoint.model}")
            continue
        payload[name] = coerce_and_validate(name, prop, value)

    for name, value in media.items():
        if not value:
            continue
        if not endpoint.declares(name):
            notes.append(f"'{name}' ignored: {endpoint.model} accepts no {name} input")
            continue
        payload[name] = value

    if extra:
        vendor: dict[str, Any] = {}
        extra_props = endpoint.properties.get("extra") or {}
        extra_props = extra_props.get("properties") if isinstance(extra_props, dict) else None
        extra_props = extra_props if isinstance(extra_props, dict) else {}
        for name, value in extra.items():
            # A long-tail parameter may be declared at the top level on one model and inside
            # the vendor passthrough on another, so route each key to wherever it belongs.
            if isinstance(endpoint.properties.get(name), dict):
                payload[name] = coerce_and_validate(name, endpoint.properties[name], value)
            elif isinstance(extra_props.get(name), dict):
                vendor[name] = coerce_and_validate(name, extra_props[name], value)
            else:
                known = ", ".join(sorted(set(endpoint.properties) | set(extra_props)))
                notes.append(f"'{name}' ignored: not supported by {endpoint.model} (accepts: {known})")
        if vendor:
            payload["extra"] = vendor

    missing = [name for name in endpoint.required if name not in payload]
    if missing:
        raise GatewayError(
            f"{endpoint.model} requires {', '.join(missing)}; set the matching tool parameter"
        )

    return payload, notes
