import json
from copy import deepcopy
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelType

from scripts.sync_catalog import CatalogError, main, normalize_catalog, render_catalog


def export_row(model_id="embedding-visible", category="embedding"):
    return {
        "id": "private-model-identifier",
        "publicModelId": model_id,
        "displayName": model_id,
        "provider": "Provider",
        "category": category,
        "enabled": True,
        "managedAvailable": True,
        "status": "available",
        "contextLength": 8191,
        "maxOutputTokens": None,
        "capabilities": [],
        "deprecated": False,
        "inputPricePer1m": "0.02",
        "outputPricePer1m": None,
        "cachePricePer1m": None,
    }


def test_export_generates_embedding_and_rerank_without_private_metadata():
    payload = {"items": [export_row(), export_row("rerank-visible", "rerank")]}
    catalog = normalize_catalog(payload)
    assert "private-model-identifier" not in json.dumps(catalog)
    assert catalog == normalize_catalog({"items": list(reversed(payload["items"]))})
    for kind, model_id, expected_type in [
        ("text_embedding", "embedding-visible", ModelType.TEXT_EMBEDDING),
        ("rerank", "rerank-visible", ModelType.RERANK),
    ]:
        files = render_catalog(catalog, model_type=kind)
        entity = AIModelEntity.model_validate(yaml.safe_load(files[f"{model_id}.yaml"]))
        assert entity.model == model_id
        assert entity.model_type == expected_type
        assert yaml.safe_load(files["_position.yaml"]) == [model_id]


def test_export_excludes_disabled_unavailable_and_non_chat_decision_routes():
    rows = [
        export_row(),
        {**export_row("disabled"), "enabled": False},
        {**export_row("unavailable"), "status": "unavailable", "managedAvailable": False},
        {**export_row("unmanaged"), "managedAvailable": False},
        export_row("decision-route", "decision"),
    ]
    assert [m["id"] for m in normalize_catalog({"items": rows})["models"]] == ["embedding-visible"]


def test_all_types_validate_before_writing_and_check_detects_drift(tmp_path):
    payload = {"items": [export_row(), export_row("rerank-visible", "rerank")]}
    source = tmp_path / "export.json"
    source.write_text(json.dumps(payload))
    args = ["sync_catalog.py", "--input", str(source), "--model-type", "all"]
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", args):
        assert main() == 0
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", [*args, "--check"]):
        assert main() == 0
    target = tmp_path / "models/text_embedding/embedding-visible.yaml"
    target.write_text("changed")
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", [*args, "--check"]):
        assert main() == 1
    before = {p: p.read_bytes() for p in (tmp_path / "models").rglob("*.yaml")}
    payload["items"][1]["provider"] = None
    source.write_text(json.dumps(payload))
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", args):
        assert main() == 1
    assert before == {p: p.read_bytes() for p in (tmp_path / "models").rglob("*.yaml")}


@pytest.mark.parametrize(
    "model_id",
    [
        "gpt-5.4",
        "gpt-6-sol",
        "o3",
        "claude-opus-5-5",
        "gemini-3.5-pro",
        "grok-4.7",
        "qwen3.5-plus",
        "deepseek-v5",
        "glm-6",
        "kimi-k4",
        "minimax-m3",
    ],
)
def test_new_reasoning_families_do_not_send_unverified_sampling(model_id):
    row = export_row(model_id, "reasoning")
    row.update(capabilities=["streaming", "reasoning"], outputPricePer1m="0.04")
    files = render_catalog(normalize_catalog({"items": [row]}))
    entity = yaml.safe_load(next(v for k, v in files.items() if k != "_position.yaml"))
    names = {rule["name"] for rule in entity["parameter_rules"]}
    assert not names & {"temperature", "top_p", "presence_penalty", "frequency_penalty"}


def test_plain_openai_listing_cannot_replace_metadata():
    with pytest.raises(CatalogError, match="metadata"):
        normalize_catalog({"data": [{"id": "model-without-metadata"}]})


def test_new_audio_models_use_metadata_instead_of_model_id_allowlists():
    from test_speech2text_catalog import catalog as stt_catalog
    from test_tts_catalog import catalog as tts_catalog

    for kind, source in [("tts", tts_catalog()), ("speech2text", stt_catalog())]:
        source = deepcopy(source)
        source["models"][0]["id"] = "new-audio-model"
        files = render_catalog(source, model_type=kind)
        assert "new-audio-model.yaml" in files


def test_dify_registers_and_invokes_generated_embedding_without_schema_injection():
    from dify_plugin.config.config import DifyPluginEnv
    from dify_plugin.core.plugin_registration import PluginRegistration
    from test_non_llm import response

    model = PluginRegistration(DifyPluginEnv()).get_model_instance(
        "tokener", ModelType.TEXT_EMBEDDING
    )
    assert model.model_schemas
    selected = model.model_schemas[0].model
    texts = [f"sample-{i}" for i in range(33)]

    def reply(*args, **kwargs):
        batch = kwargs["json"]["input"]
        return response(
            {
                "data": [
                    {"index": i, "embedding": [float(text.split("-")[-1]), 0.2]}
                    for i, text in reversed(list(enumerate(batch)))
                ],
                "usage": {"total_tokens": len(batch)},
            }
        )

    with patch("requests.post", side_effect=reply) as post:
        result = model.invoke(selected, {"api_key": "test"}, texts)
    assert result.embeddings == [[float(i), 0.2] for i in range(33)]
    assert post.call_count == 2
    assert [call.kwargs["json"]["input"] for call in post.call_args_list] == [
        texts[:32],
        texts[32:],
    ]
    assert all(
        call.args == ("https://api.tokener.ai/v1/embeddings",) for call in post.call_args_list
    )
    assert all(call.kwargs["json"]["model"] == selected for call in post.call_args_list)


def test_complete_snapshot_removes_absent_categories_and_unbacked_models(tmp_path):
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps({"items": [export_row()]}))
    for kind in ("llm", "text_embedding", "rerank", "tts", "speech2text"):
        output = tmp_path / "models" / kind
        output.mkdir(parents=True)
        (output / "stale.yaml").write_text("model: stale\n")
    args = ["sync_catalog.py", "--input", str(source), "--model-type", "all"]
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", args):
        assert main() == 0
    assert not list((tmp_path / "models").rglob("stale.yaml"))
    assert yaml.safe_load((tmp_path / "models/rerank/_position.yaml").read_text()) == []
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", [*args, "--check"]):
        assert main() == 0
    source.write_text(json.dumps({"items": []}))
    with patch("scripts.sync_catalog.ROOT", tmp_path), patch("sys.argv", args):
        assert main() == 0
    assert not list((tmp_path / "models").rglob("embedding-visible.yaml"))


@pytest.mark.parametrize(
    "kind,category",
    [
        ("llm", "chat"),
        ("text_embedding", "embedding"),
        ("rerank", "rerank"),
    ],
)
def test_labels_use_public_model_ids_in_both_languages(kind, category):
    row = export_row("public-id", category)
    row.update(
        displayName="Private display label", capabilities=["streaming"], outputPricePer1m="0.04"
    )
    catalog = normalize_catalog({"items": [row]})
    entity = yaml.safe_load(render_catalog(catalog, model_type=kind)["public-id.yaml"])
    assert entity["label"] == {"en_US": "public-id", "zh_Hans": "public-id"}


def test_unknown_category_reports_category_and_public_id():
    with pytest.raises(CatalogError) as caught:
        normalize_catalog({"items": [export_row("public-id", "unsupported-kind")]})
    assert "unsupported-kind" in str(caught.value)
    assert "public-id" in str(caught.value)


def test_unknown_category_without_managed_availability_is_skipped():
    row = export_row("unavailable-model", "unsupported-kind")
    row["managedAvailable"] = False
    assert normalize_catalog({"items": [row]})["models"] == []


def test_html_snapshot_identifies_login_page():
    from scripts.sync_catalog import decode_catalog

    with pytest.raises(CatalogError) as caught:
        decode_catalog(b" \n<!DOCTYPE html><title>Sign in</title>")
    assert "HTML login page" in str(caught.value)
    assert "re-authenticate" in str(caught.value).lower()


def test_dify_registry_matches_generated_model_positions():
    from pathlib import Path

    from dify_plugin.config.config import DifyPluginEnv
    from dify_plugin.core.plugin_registration import PluginRegistration

    registration = PluginRegistration(DifyPluginEnv())
    for kind, model_type in [
        ("llm", ModelType.LLM),
        ("text_embedding", ModelType.TEXT_EMBEDDING),
        ("rerank", ModelType.RERANK),
        ("tts", ModelType.TTS),
        ("speech2text", ModelType.SPEECH2TEXT),
    ]:
        expected = yaml.safe_load((Path("models") / kind / "_position.yaml").read_text())
        actual = registration.get_model_instance("tokener", model_type).model_schemas
        assert {schema.model for schema in actual} == set(expected)
        for schema in actual:
            assert schema.label.en_us == schema.model
            assert schema.label.zh_hans == schema.model
