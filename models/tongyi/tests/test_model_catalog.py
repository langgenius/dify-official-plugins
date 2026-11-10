"""Validate the published catalog, including schemas discovered by wildcards."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import TongyiLargeLanguageModel

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((PLUGIN_DIR / "provider" / "tongyi.yaml").read_text())


@pytest.mark.parametrize("model_type", PROVIDER["models"])
def test_registered_schemas_and_positions_are_consistent(model_type: str) -> None:
    config = PROVIDER["models"][model_type]
    schemas = []
    for pattern in config["predefined"]:
        for path in PLUGIN_DIR.glob(pattern):
            if not path.name.startswith("_"):
                schemas.append(AIModelEntity.model_validate(yaml.safe_load(path.read_text())))
    names = [schema.model for schema in schemas]
    assert names
    assert len(names) == len(set(names))
    if "position" in config:
        position = yaml.safe_load((PLUGIN_DIR / config["position"]).read_text())
        assert len(position) == len(set(position))
        assert set(position) == set(names)


def test_qwen_mt_flash_uses_translation_options() -> None:
    schema = AIModelEntity.model_validate(
        yaml.safe_load((PLUGIN_DIR / "models" / "llm" / "qwen-mt-flash.yaml").read_text())
    )
    model = TongyiLargeLanguageModel(model_schemas=[schema])
    with (
        patch("models.llm.llm.Generation.call") as call,
        patch.object(model, "_handle_generate_response", return_value="translation"),
    ):
        result = model._generate(
            model="qwen-mt-flash",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters={
                "source_lang": "English",
                "target_lang": "Chinese",
                "domains": "Technical documentation",
            },
            stream=True,
        )

    assert result == "translation"
    call.assert_called_once()
    kwargs = call.call_args.kwargs
    assert kwargs["model"] == "qwen-mt-flash"
    assert kwargs["translation_options"] == {
        "source_lang": "English",
        "target_lang": "Chinese",
        "domains": "Technical documentation",
    }
    assert kwargs["stream"] is False
    assert kwargs["messages"] == [{"role": "user", "content": "Hello"}]
