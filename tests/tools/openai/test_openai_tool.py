import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_DIR = Path("tools") / "openai"


class FakeToolInvokeMessage:
    pass


class FakeToolProviderCredentialValidationError(Exception):
    pass


def install_dify_plugin_stubs():
    dify_plugin_module = types.ModuleType("dify_plugin")

    class FakeTool:
        response_type = FakeToolInvokeMessage

        def create_text_message(self, text):
            return text

        def create_blob_message(self, blob=None, meta=None, save_as=None):
            return {"blob": blob, "meta": meta, "save_as": save_as}

        def create_json_message(self, payload):
            return payload

    class FakeToolProvider:
        pass

    dify_plugin_module.Tool = FakeTool
    dify_plugin_module.ToolProvider = FakeToolProvider

    entities_module = types.ModuleType("dify_plugin.entities")
    entities_tool_module = types.ModuleType("dify_plugin.entities.tool")
    entities_tool_module.ToolInvokeMessage = FakeToolInvokeMessage

    errors_module = types.ModuleType("dify_plugin.errors")
    errors_tool_module = types.ModuleType("dify_plugin.errors.tool")
    errors_tool_module.ToolProviderCredentialValidationError = (
        FakeToolProviderCredentialValidationError
    )

    sys.modules["dify_plugin"] = dify_plugin_module
    sys.modules["dify_plugin.entities"] = entities_module
    sys.modules["dify_plugin.entities.tool"] = entities_tool_module
    sys.modules["dify_plugin.errors"] = errors_module
    sys.modules["dify_plugin.errors.tool"] = errors_tool_module


install_dify_plugin_stubs()


def load_module_from_path(module_name: str, file_path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader, f"cannot load spec for {module_name} from {file_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def import_plugin_module(module_name: str, relative_path: str) -> types.ModuleType:
    plugin_root = str(PLUGIN_DIR.resolve())
    sys.path.insert(0, plugin_root)
    try:
        return load_module_from_path(module_name, PLUGIN_DIR / relative_path)
    finally:
        sys.path.pop(0)


def create_tool_instance(tool_cls):
    tool = tool_cls.__new__(tool_cls)
    tool.response_type = FakeToolInvokeMessage
    tool.runtime = MagicMock()
    return tool


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("http://host:8317", "http://host:8317/v1"),
        ("  http://host:8317  ", "http://host:8317/v1"),
        ("http://host:8317/", "http://host:8317/v1"),
        ("http://host:8317/v1", "http://host:8317/v1"),
        ("http://host:8317/v1/", "http://host:8317/v1"),
    ],
)
def test_normalize_openai_base_url(raw_url, expected):
    helpers = import_plugin_module("openai_helpers", "openai_client.py")
    assert helpers.normalize_openai_base_url(raw_url) == expected


def test_provider_validate_credentials_uses_models_list():
    provider_module = import_plugin_module("openai_provider", "provider/openai.py")
    provider = provider_module.OpenAIProvider.__new__(provider_module.OpenAIProvider)

    mock_client = MagicMock()
    mock_client.models.list.return_value = [{"id": "gpt-image-1"}]

    with patch.object(provider_module, "OpenAI", return_value=mock_client) as mock_openai:
        provider._validate_credentials(
            {
                "openai_api_key": "test-key",
                "openai_base_url": "http://host:8317/v1",
                "openai_organization_id": "org-test",
            }
        )

    mock_openai.assert_called_once_with(
        api_key="test-key",
        base_url="http://host:8317/v1",
        organization="org-test",
    )
    mock_client.models.list.assert_called_once_with()


def test_provider_validate_credentials_wraps_errors():
    provider_module = import_plugin_module("openai_provider", "provider/openai.py")
    provider = provider_module.OpenAIProvider.__new__(provider_module.OpenAIProvider)

    mock_client = MagicMock()
    mock_client.models.list.side_effect = RuntimeError("bad credentials")

    with patch.object(provider_module, "OpenAI", return_value=mock_client):
        with pytest.raises(FakeToolProviderCredentialValidationError, match="bad credentials"):
            provider._validate_credentials(
                {
                    "openai_api_key": "test-key",
                    "openai_base_url": "http://host:8317",
                }
            )


def test_gpt_image_2_generate_uses_normalized_base_url():
    tool_module = import_plugin_module("gpt_image_2_generate_tool", "tools/gpt_image_2_generate.py")
    tool = create_tool_instance(tool_module.GPTImage2GenerateTool)
    tool.runtime.credentials = {
        "openai_api_key": "test-key",
        "openai_base_url": "http://host:8317/v1/",
        "openai_organization_id": "org-test",
    }

    mock_client = MagicMock()
    mock_client.images.generate.side_effect = RuntimeError("network failed")

    with patch.object(tool_module, "OpenAI", return_value=mock_client) as mock_openai:
        results = list(tool._invoke({"prompt": "a cat"}))

    mock_openai.assert_called_once_with(
        api_key="test-key",
        base_url="http://host:8317/v1",
        organization="org-test",
    )
    assert len(results) == 1
    assert "Failed to generate image: network failed" in str(results[0])
