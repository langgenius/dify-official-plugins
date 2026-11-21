import json

import pytest
import yaml

from models.llm._wire import TRANSPORT_FIELDS
from scripts.source_contracts import apply_source_contracts, load_source_contracts
from scripts.sync_catalog import LLM_DIR, SOURCE_ROOT, CatalogError, sync_files


def test_source_rules_and_provider_mapping_are_reproducible_and_drift_is_detected(tmp_path):
    contracts = load_source_contracts(SOURCE_ROOT)
    files = {path.name: path.read_text() for path in LLM_DIR.glob("*.yaml")}
    generated = apply_source_contracts(files.copy(), contracts)
    assert generated == {name: (LLM_DIR / name).read_text() for name in generated}
    for name, body in generated.items():
        if name.startswith("_"):
            continue
        rules = yaml.safe_load(body)["parameter_rules"]
        assert not TRANSPORT_FIELDS & {rule["name"] for rule in rules}
    sync_files(generated, check=False, output_dir=tmp_path)
    assert sync_files(generated, check=True, output_dir=tmp_path)
    target = tmp_path / "claude-sonnet-5.yaml"
    target.write_text(target.read_text().replace("default: 128000", "default: 4096"))
    assert not sync_files(generated, check=True, output_dir=tmp_path)
    target.write_text(generated[target.name])
    (tmp_path / "_provider_models.json").write_text(json.dumps({"glm-5": "openai"}))
    assert not sync_files(generated, check=True, output_dir=tmp_path)


def test_missing_source_provider_is_rejected(tmp_path):
    with pytest.raises(CatalogError):
        load_source_contracts(tmp_path)
