import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey, ModelType

from models._credentials import ENDPOINT_URL
from scripts.sync_catalog import main, normalize_catalog, render_catalog


@pytest.fixture
def source_models(tmp_path):
    root = tmp_path / "source-models"
    for provider, names in [
        ("openai", ["gpt-4o-mini"]),
        ("gemini", ["gemini-2.5-pro"]),
        ("anthropic", ["claude-sonnet-4-6"]),
        ("tongyi", ["qwen-mt-plus", "deepseek-v4-pro"]),
        ("x", ["grok-4.5"]),
    ]:
        directory = root / provider / "models/llm"
        directory.mkdir(parents=True)
        (root / provider / "manifest.yaml").write_text(
            yaml.safe_dump({"name": provider, "version": "1.0.0"})
        )
        for name in names:
            schema = yaml.safe_load(Path(f"models/llm/{name}.yaml").read_text())
            if provider == "gemini":
                schema["label"] = {"en_US": "Gemini source label", "zh_Hans": "Gemini 来源标签"}
            (directory / f"{name}.yaml").write_text(yaml.safe_dump(schema))
    for index in range(8):
        schema = yaml.safe_load((root / "gemini/models/llm/gemini-2.5-pro.yaml").read_text())
        schema["model"] = f"fallback-model-{index}"
        (root / "gemini/models/llm" / f"fallback-model-{index}.yaml").write_text(
            yaml.safe_dump(schema)
        )
    return root


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


def test_export_generates_non_llm_types_without_private_metadata():
    payload = {
        "items": [
            export_row(),
            export_row("rerank-visible", "rerank"),
            export_row("omni-moderation-latest", "moderation"),
        ]
    }
    catalog = normalize_catalog(payload)
    assert "private-model-identifier" not in json.dumps(catalog)
    for kind, model_id, expected_type in [
        ("text_embedding", "embedding-visible", ModelType.TEXT_EMBEDDING),
        ("rerank", "rerank-visible", ModelType.RERANK),
        ("moderation", "omni-moderation-latest", ModelType.MODERATION),
    ]:
        files = render_catalog(catalog, model_type=kind)
        entity = AIModelEntity.model_validate(yaml.safe_load(files[f"{model_id}.yaml"]))
        assert entity.model == model_id
        assert entity.model_type == expected_type


def test_export_excludes_disabled_unavailable_and_non_chat_decision_routes():
    rows = [
        export_row(),
        {**export_row("disabled"), "enabled": False},
        {**export_row("unmanaged"), "managedAvailable": False},
        export_row("decision-route", "decision"),
    ]
    assert [m["id"] for m in normalize_catalog({"items": rows})["models"]] == ["embedding-visible"]


def test_all_types_validate_before_writing_and_check_detects_drift(
    tmp_path, monkeypatch, source_models
):
    from models import _api
    from models.llm.llm import TokenerLargeLanguageModel

    llm_row = export_row("qwen-mt-plus", "chat")
    llm_row.update(maxOutputTokens=4096, outputPricePer1m="0.04", capabilities=["streaming"])
    payload = {
        "items": [
            export_row(),
            export_row("rerank-visible", "rerank"),
            llm_row,
            {**llm_row, "publicModelId": "deepseek-v4-pro"},
        ]
    }
    source = tmp_path / "export.json"
    source.write_text(json.dumps(payload))
    args = [
        "sync_catalog.py",
        "--input",
        str(source),
        "--model-type",
        "all",
        "--source-root",
        str(source_models),
    ]
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", args),
    ):
        assert main() == 0
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", [*args, "--check"]),
    ):
        assert main() == 0
    generated = yaml.safe_load((tmp_path / "models/llm/qwen-mt-plus.yaml").read_text())
    defaults = {rule["name"]: rule.get("default") for rule in generated["parameter_rules"]}
    assert defaults["source_lang"] == "auto"
    assert defaults["target_lang"] == "Chinese"
    routes = json.loads((tmp_path / "models/llm/_provider_models.json").read_text())
    assert routes["deepseek-v4-pro"] == "tongyi"
    from scripts.source_contracts import sync_redirect_schemas

    redirect_dir = tmp_path / "refreshed/_redirect_schemas"
    assert sync_redirect_schemas(source_models, redirect_dir)
    index = json.loads((redirect_dir / "index.json").read_text())
    assert len(index["shards"]) > 1
    for shard in index["shards"]:
        for models in json.loads((redirect_dir / shard).read_text())["schemas"].values():
            for entry in models.values():
                AIModelEntity.model_validate(entry)
    monkeypatch.setattr(_api, "__file__", str(tmp_path / "refreshed/_api.py"))
    monkeypatch.setattr(_api, "_REDIRECT_SCHEMAS", None)
    monkeypatch.setattr(_api, "_STATIC_MODELS", {})
    assert _api.redirect_family("deepseek-v4-pro") == "tongyi"
    fallback = TokenerLargeLanguageModel(model_schemas=[]).get_customizable_model_schema(
        "gemini-2.5-pro", {}
    )
    assert fallback is not None
    source_model = yaml.safe_load(
        (source_models / "gemini/models/llm/gemini-2.5-pro.yaml").read_text()
    )
    assert fallback.label.en_us == source_model["label"]["en_US"]
    assert fallback.label.zh_hans == source_model["label"]["zh_Hans"]
    target = tmp_path / "models/text_embedding/embedding-visible.yaml"
    target.write_text("changed")
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", [*args, "--check"]),
    ):
        assert main() == 1
    before = {p: p.read_bytes() for p in (tmp_path / "models").rglob("*.yaml")}
    payload["items"][0]["contextLength"] = 0
    source.write_text(json.dumps(payload))
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", args),
    ):
        assert main() == 1
    assert before == {p: p.read_bytes() for p in (tmp_path / "models").rglob("*.yaml")}


def test_new_audio_models_use_metadata_instead_of_model_id_allowlists():
    from test_speech2text_catalog import catalog as stt_catalog
    from test_tts_catalog import catalog as tts_catalog

    for kind, source in [("tts", tts_catalog()), ("speech2text", stt_catalog())]:
        source = deepcopy(source)
        source["models"][0]["id"] = "new-audio-model"
        files = render_catalog(source, model_type=kind)
        assert "new-audio-model.yaml" in files


def test_dify_registers_and_invokes_generated_embedding_without_schema_injection():
    import tiktoken
    from dify_plugin.config.config import DifyPluginEnv
    from dify_plugin.core.plugin_registration import PluginRegistration
    from test_non_llm import response

    model = PluginRegistration(DifyPluginEnv()).get_model_instance(
        "tokener", ModelType.TEXT_EMBEDDING
    )
    assert model.model_schemas
    selected = "text-embedding-3-small"
    encoding = tiktoken.encoding_for_model(selected)
    texts = [f"sample-{i}" for i in range(33)]

    def reply(*args, **kwargs):
        batch = kwargs["json"]["input"]
        return response(
            {
                "data": [
                    {"index": i, "embedding": [float(encoding.decode(text).split("-")[-1]), 0.2]}
                    for i, text in reversed(list(enumerate(batch)))
                ],
                "usage": {"total_tokens": len(batch)},
            }
        )

    with patch("requests.post", side_effect=reply) as post:
        result = model.invoke(selected, {"api_key": "test"}, texts)
    for i, vector in enumerate(result.embeddings):
        norm = (i * i + 0.04) ** 0.5
        assert vector == pytest.approx([i / norm, 0.2 / norm])
    assert post.call_count == 2
    assert [call.kwargs["json"]["input"] for call in post.call_args_list] == [
        [encoding.encode(text) for text in texts[:32]],
        [encoding.encode(text) for text in texts[32:]],
    ]
    assert all(call.args == (f"{ENDPOINT_URL}/embeddings",) for call in post.call_args_list)
    assert all(call.kwargs["json"]["model"] == selected for call in post.call_args_list)


def test_complete_snapshot_removes_absent_categories_and_unbacked_models(tmp_path, source_models):
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps({"items": [export_row()]}))
    for kind in ("llm", "text_embedding", "rerank", "tts", "speech2text"):
        output = tmp_path / "models" / kind
        output.mkdir(parents=True)
        (output / "stale.yaml").write_text("model: stale\n")
    args = [
        "sync_catalog.py",
        "--input",
        str(source),
        "--model-type",
        "all",
        "--source-root",
        str(source_models),
    ]
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", args),
    ):
        assert main() == 0
    assert not list((tmp_path / "models").rglob("stale.yaml"))
    assert yaml.safe_load((tmp_path / "models/rerank/_position.yaml").read_text()) == []
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", [*args, "--check"]),
    ):
        assert main() == 0
    source.write_text(json.dumps({"items": []}))
    with (
        patch("scripts.sync_catalog.ROOT", tmp_path),
        patch("scripts.sync_catalog.REDIRECT_DIR", tmp_path / "models/_redirect_schemas"),
        patch("sys.argv", args),
    ):
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
        ("moderation", ModelType.MODERATION),
    ]:
        expected = yaml.safe_load((Path("models") / kind / "_position.yaml").read_text())
        actual = registration.get_model_instance("tokener", model_type).model_schemas
        assert {schema.model for schema in actual} == set(expected)


@pytest.mark.parametrize("model_id", ["text-embedding-v3", "text-embedding-v4"])
def test_dashscope_embedding_sync_preserves_provider_batch_limit(model_id):
    row = export_row(model_id)
    row.update(contextLength=8192, inputPricePer1m="0.070000", provider="Alibaba")
    files = render_catalog(normalize_catalog({"items": [row]}), model_type="text_embedding")
    schema = AIModelEntity.model_validate(yaml.safe_load(files[f"{model_id}.yaml"]))
    assert schema.model_properties[ModelPropertyKey.MAX_CHUNKS] == 10
