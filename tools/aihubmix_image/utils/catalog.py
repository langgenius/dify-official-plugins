"""The model dropdown: which image models the gateway is currently serving.

Dify's ``dynamic-select`` parameter type calls back into the plugin to fill the options, so
the list comes from ``GET /api/v1/models`` at runtime instead of being frozen into the YAML.
That is the whole point of the rewrite: AIHubMix adds image models faster than a released
plugin version can follow.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from utils.client import AIHubMixClient, GatewayError

CATALOG_PATH = "/api/v1/models?type=image_generation&sort_by=order"
CATALOG_CACHE_TTL = 300

_CATALOG_CACHE: dict[str, tuple[float, list["CatalogModel"]]] = {}


@dataclass(frozen=True)
class CatalogModel:
    model_id: str
    display_name: str
    accepts_image: bool


def list_image_models(client: AIHubMixClient, *, accepts_image: bool = False) -> list[CatalogModel]:
    """Active image models, optionally narrowed to those that accept image input."""
    models = _load(client)
    return [model for model in models if model.accepts_image] if accepts_image else list(models)


def _load(client: AIHubMixClient) -> list[CatalogModel]:
    cached = _CATALOG_CACHE.get(client.base_url)
    now = time.monotonic()
    if cached and now - cached[0] < CATALOG_CACHE_TTL:
        return cached[1]

    models = _parse(client.get_json(CATALOG_PATH))
    if not models:
        raise GatewayError(
            "The gateway returned no image models for this key. Check the API Base URL and "
            "that the key is allowed to list models."
        )

    _CATALOG_CACHE[client.base_url] = (now, models)
    return models


def _parse(payload: Any) -> list[CatalogModel]:
    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    models: list[CatalogModel] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("model_id") or item.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        if str(item.get("retire_stage") or "active").lower() != "active":
            continue
        # schema_checked marks the models whose unified-endpoint schema the gateway has
        # verified. Everything else is either not served there at all (endpoint discovery
        # answers 404) or served from an unreviewed schema, so it stays out of the dropdown
        # rather than being maintained as a hand-written exclusion list here.
        if not item.get("schema_checked"):
            continue
        # The -free tiers are rate-limited trial models that answer model_unavailable most of
        # the time; offering them in the dropdown only produces failed runs.
        if model_id.endswith("-free"):
            continue
        seen.add(model_id)
        modalities = str(item.get("input_modalities") or "")
        models.append(
            CatalogModel(
                model_id=model_id,
                display_name=str(item.get("model_name") or model_id),
                accepts_image="image" in modalities,
            )
        )
    return models
