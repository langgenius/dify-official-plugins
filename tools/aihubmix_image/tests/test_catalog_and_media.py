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


def test_only_schema_checked_models_are_offered():
    models = catalog.list_image_models(FakeClient(CATALOG))
    ids = {model.model_id for model in models}
    expected = {
        item["model_id"]
        for item in CATALOG["data"]
        if item.get("schema_checked") and item.get("retire_stage") == "active"
        and not item["model_id"].endswith("-free")
    }
    assert ids == expected
    # Unchecked entries include both the ones discovery answers 404 for and ones that are
    # served but from an unreviewed schema.
    assert "dall-e-3" not in ids
    assert "doubao-seedream-4-5" not in ids
    assert "gpt-image-2" in ids


def test_free_tier_models_are_hidden():
    ids = {model.model_id for model in catalog.list_image_models(FakeClient(CATALOG))}
    assert "gpt-image-2-free" not in ids
    assert "gemini-3.1-flash-image-preview-free" not in ids


def test_edit_dropdown_only_offers_models_that_take_an_image():
    models = catalog.list_image_models(FakeClient(CATALOG), accepts_image=True)
    ids = {model.model_id for model in models}
    assert "gpt-image-2" in ids
    assert "glm-image" not in ids  # text-only


def test_a_failed_catalog_call_surfaces_instead_of_guessing():
    # A hand-written fallback list would go stale silently; the gateway error is the truth.
    with pytest.raises(GatewayError):
        catalog.list_image_models(FakeClient(fail=True))


def test_an_empty_catalog_says_so():
    with pytest.raises(GatewayError, match="no image models"):
        catalog.list_image_models(FakeClient({"data": []}))


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


def test_the_model_parameter_sits_in_the_section_that_can_fetch_its_options():
    """Dify's workflow tool panel splits parameters into an input-variable list and a
    settings list, and only the input-variable list is handed the provider/tool context
    that `dynamic-select` needs to call dynamic-options. A `form: form` dynamic-select
    therefore renders as a permanently empty dropdown, so `model` must stay `form: llm`.
    """
    import yaml

    root = Path(__file__).resolve().parents[1]
    for name in ("image-generate", "image-edit"):
        declaration = yaml.safe_load((root / "tools" / f"{name}.yaml").read_text())
        model = next(p for p in declaration["parameters"] if p["name"] == "model")
        assert model["type"] == "dynamic-select", name
        assert model["form"] == "llm", name


def test_both_tools_prefill_the_same_default_model():
    """Dify fills a new node's parameters from the static declaration, so the dropdown only
    starts on a model if one is named here. Edit narrows the catalog to models that accept
    image input, so the shared default has to be one of those."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    defaults = {
        name: next(
            p for p in yaml.safe_load((root / "tools" / f"{name}.yaml").read_text())["parameters"]
            if p["name"] == "model"
        )["default"]
        for name in ("image-generate", "image-edit")
    }
    assert defaults["image-generate"] == defaults["image-edit"]
    assert defaults["image-generate"]


def test_the_plugin_files_itself_under_the_image_category():
    """Without a tag the plugin lands in no category at all -- Dify shows it only under the
    catch-all tool listing, never under Image. The tag has to be declared in both places:
    the manifest drives the plugin list, the provider identity drives the tool picker."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / "manifest.yaml").read_text())
    provider = yaml.safe_load((root / "provider" / "aihubmix-image.yaml").read_text())
    assert "image" in manifest["tags"]
    assert "image" in provider["identity"]["tags"]


def test_the_provider_label_is_something_a_user_would_search_for():
    """The tool picker matches the typed keyword against provider/tool `name` and `label` and
    nothing else -- descriptions are not searched. A label that just repeats the provider id
    means the plugin cannot be found by what it does."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    identity = yaml.safe_load((root / "provider" / "aihubmix-image.yaml").read_text())["identity"]
    label = identity["label"]
    assert label["en_US"] != identity["name"]
    assert "图片" in label["zh_Hans"]
