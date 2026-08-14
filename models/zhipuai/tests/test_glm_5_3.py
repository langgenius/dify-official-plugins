import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from models.llm.llm import ZhipuAILargeLanguageModel


def test_glm_5_3_schema_and_request_parameters() -> None:
    model_file = PLUGIN_DIR / "models" / "llm" / "glm-5.3.yaml"
    schema = yaml.safe_load(model_file.read_text(encoding="utf-8"))
    AIModelEntity.model_validate(schema)

    position = yaml.safe_load(
        (model_file.parent / "_position.yaml").read_text(encoding="utf-8")
    )
    assert position[0] == "glm-5.3"

    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
    assert schema["model_properties"]["context_size"] == 1_000_000
    assert rules["max_tokens"]["max"] == 131_072
    assert rules["reasoning_effort"]["options"] == ["low", "high", "max"]
    assert rules["reasoning_effort"]["default"] == "max"
    assert "thinking" not in rules
    assert "pricing" not in schema

    client = MagicMock()
    result = object()
    llm = ZhipuAILargeLanguageModel(model_schemas=[])
    with (
        patch("models.llm.llm.ZhipuAiClient", return_value=client),
        patch.object(
            ZhipuAILargeLanguageModel,
            "_handle_generate_response",
            return_value=result,
        ),
    ):
        actual = llm._generate(
            model="glm-5.3",
            credentials_kwargs={"api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters={"thinking": False, "reasoning_effort": "low"},
            stream=False,
        )

    assert actual is result
    client.chat.completions.create.assert_called_once_with(
        model="glm-5.3",
        messages=[{"role": "user", "content": "hello"}],
        thinking={"type": "enabled"},
        reasoning_effort="low",
    )
