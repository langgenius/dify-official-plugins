from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.sync_catalog import GENERATED_MARKER, CatalogError, render_catalog, sync_files


def _catalog() -> dict:
    return {
        "schemaVersion": 1,
        "catalogRevision": f"sha256:{'a' * 64}",
        "models": [
            {
                "id": "model-b",
                "label": "Model B",
                "provider": "provider",
                "modelType": "llm",
                "mode": "chat",
                "contextSize": 200000,
                "maxOutputTokens": 4096,
                "capabilities": [
                    "streaming",
                    "tool_calling",
                    "parallel_tool_calling",
                    "streaming_tool_calls",
                    "structured_output",
                ],
                "pricing": {
                    "currency": "USD",
                    "inputPerMillion": "1.000000",
                    "outputPerMillion": "5.000000",
                    "cacheReadPerMillion": None,
                },
                "deprecated": False,
            },
            {
                "id": "model-a",
                "label": "Model A",
                "provider": "provider",
                "modelType": "llm",
                "mode": "chat",
                "contextSize": 100000,
                "maxOutputTokens": None,
                "capabilities": ["streaming"],
                "pricing": {
                    "currency": "USD",
                    "inputPerMillion": "0.100000",
                    "outputPerMillion": "0.200000",
                    "cacheReadPerMillion": "0.010000",
                },
                "deprecated": True,
            },
            {
                "id": "embedding-ignored",
                "modelType": "text-embedding",
            },
        ],
    }


def test_render_and_check_catalog(tmp_path: Path) -> None:
    files = render_catalog(_catalog())

    assert list(files) == ["model-a.yaml", "model-b.yaml", "_position.yaml"]
    assert yaml.safe_load(files["_position.yaml"]) == ["model-a", "model-b"]

    model_a = yaml.safe_load(files["model-a.yaml"])
    assert model_a["features"] == []
    rules_a = {rule["name"]: rule for rule in model_a["parameter_rules"]}
    assert list(rules_a) == ["max_tokens"]
    assert rules_a["max_tokens"]["min"] == 1
    assert rules_a["max_tokens"]["default"] == 8192
    assert rules_a["max_tokens"]["max"] == 65536

    model_b = yaml.safe_load(files["model-b.yaml"])
    assert model_b["features"] == [
        "tool-call",
        "multi-tool-call",
        "stream-tool-call",
        "structured-output",
    ]
    rules_b = {rule["name"]: rule for rule in model_b["parameter_rules"]}
    assert list(rules_b) == ["max_tokens", "response_format", "json_schema"]
    assert rules_b["max_tokens"]["default"] == 4096
    assert rules_b["max_tokens"]["max"] == 4096
    assert rules_b["response_format"]["options"] == ["text", "json_object", "json_schema"]
    assert rules_b["json_schema"]["use_template"] == "json_schema"

    assert sync_files(files, check=False, output_dir=tmp_path)
    assert sync_files(files, check=True, output_dir=tmp_path)

    (tmp_path / "stale.yaml").write_text(f"{GENERATED_MARKER}\n", encoding="utf-8")
    assert not sync_files(files, check=True, output_dir=tmp_path)
    assert sync_files(files, check=False, output_dir=tmp_path)
    assert not (tmp_path / "stale.yaml").exists()


def test_rejects_unknown_capability() -> None:
    catalog = deepcopy(_catalog())
    catalog["models"][0]["capabilities"].append("future-capability")

    with pytest.raises(CatalogError, match="unknown values"):
        render_catalog(catalog)
