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

# Listed in the catalog but not served by the unified endpoint — discovery answers 404, so
# showing them in the dropdown would only produce a failure at invoke time.
UNSUPPORTED_MODELS = frozenset({
    "imagen-4.0",
    "imagen-4.0-ultra",
    "FLUX-1.1-pro",
    "dall-e-3",
    "dall-e-2",
    "gpt-image-1.5",
    "doubao-seedream-5.0-pro",
    "gpt-image-1",
    "gpt-image-1-mini",
    # The Ideogram catalog entries are legacy aliases kept for the old passthrough routes.
    "V_1",
    "V_1_TURBO",
    "V_2",
    "V_2_TURBO",
    "V_2A",
    "V_2A_TURBO",
    "UPSCALE",
    "DESCRIBE",
})

# Used only when the catalog call itself fails (network, proxy, expired key); a stale
# dropdown still lets the user work, an empty one does not.
FALLBACK_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-image-2", "GPT Image 2"),
    ("gpt-image-2.5-flare", "GPT Image 2.5 Flare"),
    ("gemini-3-pro-image", "Gemini 3 Pro Image"),
    ("gemini-3.1-flash-image", "Gemini 3.1 Flash Image"),
    ("doubao-seedream-4-5", "Doubao Seedream 4.5"),
    ("doubao-seedream-5.0-lite", "Doubao Seedream 5.0 Lite"),
    ("qwen-image-2.0", "Qwen Image 2.0"),
    ("qwen-image-3.0", "Qwen Image 3.0"),
    ("flux-2-pro", "Flux 2 Pro"),
    ("glm-image", "GLM Image"),
    ("wan2.7-image", "Wan2.7 Image"),
    ("mai-image-2.6-flash", "Mai Image 2.6 Flash"),
)

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

    try:
        payload = client.get_json(CATALOG_PATH)
        models = _parse(payload)
    except GatewayError:
        models = []

    if not models:
        return [CatalogModel(model_id=mid, display_name=name, accepts_image=True) for mid, name in FALLBACK_MODELS]

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
        if not model_id or model_id in seen or model_id in UNSUPPORTED_MODELS:
            continue
        if str(item.get("retire_stage") or "active").lower() != "active":
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
