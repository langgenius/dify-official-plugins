"""The model dropdown and the file-to-media-reference conversion."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import catalog, media  # noqa: E402
from utils.client import GatewayError  # noqa: E402
from utils.schema import _select_unified_endpoint  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = json.loads((FIXTURES / "_catalog_image_generation.json").read_text())


class FakeClient:
    base_url = "https://api.inferera.com"

    def __init__(self, payload=None, *, fail=False):
        self.payload = payload
        self.fail = fail

    def get_json(self, path, **kwargs):
        if self.fail:
            raise GatewayError("gateway unreachable", status=503)
        return self.payload


class FakeFile:
    def __init__(self, blob, mime_type="image/png"):
        self.blob = blob
        self.mime_type = mime_type


@pytest.fixture(autouse=True)
def clear_cache():
    catalog._CATALOG_CACHE.clear()
    yield
    catalog._CATALOG_CACHE.clear()


def endpoint_for(model: str):
    return _select_unified_endpoint(json.loads((FIXTURES / f"{model}.json").read_text()), model)


def test_catalog_lists_active_models_only():
    models = catalog.list_image_models(FakeClient(CATALOG))
    ids = {model.model_id for model in models}

    retired = {
        item["model_id"]
        for item in CATALOG["data"]
        if item.get("retire_stage") != "active"
    }
    assert ids and not (ids & retired)


def test_models_the_unified_endpoint_cannot_serve_are_hidden():
    ids = {model.model_id for model in catalog.list_image_models(FakeClient(CATALOG))}
    # These are listed in the catalog but answer 404 on endpoint discovery.
    assert "dall-e-3" not in ids
    assert "imagen-4.0" not in ids
    assert "gpt-image-2" in ids


def test_edit_dropdown_only_offers_models_that_take_an_image():
    models = catalog.list_image_models(FakeClient(CATALOG), accepts_image=True)
    ids = {model.model_id for model in models}
    assert "gpt-image-2" in ids
    assert "glm-image" not in ids  # text-only


def test_dropdown_falls_back_when_the_catalog_call_fails():
    models = catalog.list_image_models(FakeClient(fail=True))
    assert models
    assert all(model.accepts_image for model in models)


def test_single_file_maps_to_the_field_the_model_declares():
    endpoint = endpoint_for("gpt-image-2")
    assigned = media.source_images(endpoint, [FakeFile(b"\x89PNG\r\n\x1a\n")])
    # gpt-image-2 declares both image and images; images is the general form.
    assert list(assigned) == ["images"]
    assert assigned["images"][0].startswith("data:image/png;base64,")
    assert base64.b64decode(assigned["images"][0].split(",", 1)[1]) == b"\x89PNG\r\n\x1a\n"


def test_url_strings_pass_through_untouched():
    endpoint = endpoint_for("gpt-image-2")
    assigned = media.source_images(endpoint, "https://example.com/a.png")
    assert assigned["images"] == ["https://example.com/a.png"]


def test_multi_image_limit_comes_from_the_schema():
    endpoint = endpoint_for("gpt-image-2")
    limit = endpoint.properties["images"]["maxItems"]
    with pytest.raises(GatewayError) as excinfo:
        media.source_images(endpoint, [FakeFile(b"x")] * (limit + 1))
    assert str(limit) in str(excinfo.value)


def test_text_only_model_rejects_image_input_with_a_pointer():
    endpoint = endpoint_for("glm-image")
    with pytest.raises(GatewayError) as excinfo:
        media.source_images(endpoint, [FakeFile(b"x")])
    assert "generate tool" in str(excinfo.value)


def test_oversized_file_is_rejected_before_the_request():
    endpoint = endpoint_for("gpt-image-2")
    with pytest.raises(GatewayError) as excinfo:
        media.source_images(endpoint, [FakeFile(b"x" * (media.MAX_INLINE_BYTES + 1))])
    assert "limit" in str(excinfo.value)
