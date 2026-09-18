import importlib.util
import io
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


class FakeFile:
    def __init__(self, blob=b"image", filename="input.png"):
        self.blob = blob
        self.filename = filename


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

    file_module = types.ModuleType("dify_plugin.file")
    file_file_module = types.ModuleType("dify_plugin.file.file")
    file_file_module.File = FakeFile

    sys.modules["dify_plugin"] = dify_plugin_module
    sys.modules["dify_plugin.entities"] = entities_module
    sys.modules["dify_plugin.entities.tool"] = entities_tool_module
    sys.modules["dify_plugin.errors"] = errors_module
    sys.modules["dify_plugin.errors.tool"] = errors_tool_module
    sys.modules["dify_plugin.file"] = file_module
    sys.modules["dify_plugin.file.file"] = file_file_module


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
        api_key="test-key", base_url="http://host:8317/v1", organization="org-test"
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
                {"openai_api_key": "test-key", "openai_base_url": "http://host:8317"}
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
        api_key="test-key", base_url="http://host:8317/v1", organization="org-test"
    )
    assert len(results) == 1
    assert "Failed to generate image: network failed" in str(results[0])


@pytest.mark.parametrize("operation", ["generate", "edit"])
@pytest.mark.parametrize(
    ("model", "quality", "output_format", "background", "size"),
    [
        (None, "high", "png", "transparent", "1024x1024"),
        ("gpt-image-2.5-flare", "xhigh", "webp", "transparent", "3840x2160"),
        ("gpt-image-2.5-sunburst", "max", "jpeg", "opaque", "1024x640"),
        ("gpt-image-2.5-flare", "auto", "auto", "transparent", "auto"),
    ],
)
def test_gpt_image_requests_and_outputs(operation, model, quality, output_format, background, size):
    module = import_plugin_module(
        f"gpt_image_2_{operation}_tool", f"tools/gpt_image_2_{operation}.py"
    )
    tool = create_tool_instance(getattr(module, f"GPTImage2{operation.title()}Tool"))
    tool.runtime.credentials = {"openai_api_key": "test-key"}
    parameters = {
        "prompt": "a cat",
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
        "output_compression": 75,
        "n": "2",
    }
    if operation == "generate":
        parameters["moderation"] = "low"
    if model:
        parameters["model"] = model
    expected = {key: value for key, value in parameters.items() if value != "auto"}
    expected.update(model=model or "gpt-image-2", n=2)
    if output_format in {"png", "auto"}:
        expected.pop("output_compression")
    if operation == "edit":
        parameters["image"] = [FakeFile(), FakeFile()] if model else FakeFile()
        parameters["mask"] = FakeFile(b"mask", "mask.png")

    usage = {"total_tokens": 15, "input_tokens": 10, "output_tokens": 5}
    response = types.SimpleNamespace(
        data=[types.SimpleNamespace(b64_json="aW1hZ2U=")] * 2, usage=types.SimpleNamespace(**usage)
    )
    client = MagicMock()
    endpoint = getattr(client.images, operation)
    endpoint.return_value = response
    with patch.object(module, "OpenAI", return_value=client):
        results = list(tool._invoke(parameters))

    endpoint.assert_called_once()
    arguments = dict(endpoint.call_args.kwargs)
    if operation == "edit":
        images = arguments.pop("image")
        images = images if isinstance(images, list) else [images]
        assert len(images) == (2 if model else 1)
        assert all(file.closed and file.name == "input.png" for file in images)
        mask = arguments.pop("mask")
        assert mask.closed and mask.name == "mask.png"
    assert arguments == expected
    assert (
        results[:2]
        == [
            {
                "blob": b"image",
                "meta": {
                    "mime_type": f"image/{'png' if output_format == 'auto' else output_format}",
                    "token_usage": usage,
                },
                "save_as": None,
            }
        ]
        * 2
    )
    assert results[2:] == [
        {
            "data": [
                {
                    "model": model or "gpt-image-2",
                    "operation": operation,
                    "image_count": 2,
                    "usage": usage,
                }
            ]
        }
    ]


@pytest.mark.parametrize("operation", ["generate", "edit"])
@pytest.mark.parametrize(
    "invalid",
    [
        {"model": "gpt-image-2.5"},
        {"model": []},
        {"model": "gpt-image-2", "quality": "xhigh"},
        {"model": "gpt-image-2", "quality": "max"},
        {"size": "1025x1024"},
        {"size": "3856x2048"},
        {"size": "3072x768"},
        {"size": "512x512"},
        {"size": "3072x3072"},
        {"size": "1024by1024"},
        {"background": "transparent", "output_format": "jpeg"},
        {"background": "invalid"},
        {"quality": "invalid"},
        {"quality": []},
        {"output_format": "gif"},
        {"output_compression": 101},
        {"output_compression": True},
        {"output_compression": 1.5},
        {"n": 0},
        {"n": 11},
        {"n": True},
        {"n": 1.5},
    ],
)
def test_gpt_image_rejects_invalid_parameters_without_api_calls(operation, invalid):
    module = import_plugin_module(
        f"gpt_image_2_{operation}_tool", f"tools/gpt_image_2_{operation}.py"
    )
    tool = create_tool_instance(getattr(module, f"GPTImage2{operation.title()}Tool"))
    tool.runtime.credentials = {"openai_api_key": "test-key"}
    parameters = {"prompt": "a cat", "model": "gpt-image-2.5-flare", **invalid}
    if operation == "edit":
        parameters["image"] = FakeFile()
    client = MagicMock()
    with patch.object(module, "OpenAI", return_value=client):
        results = list(tool._invoke(parameters))
    assert len(results) == 1 and isinstance(results[0], str)
    assert any(parameter in results[0].lower() for parameter in invalid)
    client.images.generate.assert_not_called()
    client.images.edit.assert_not_called()


def test_gpt_image_generate_rejects_invalid_moderation():
    module = import_plugin_module("gpt_image_2_generate_tool", "tools/gpt_image_2_generate.py")
    tool = create_tool_instance(module.GPTImage2GenerateTool)
    tool.runtime.credentials = {"openai_api_key": "test-key"}
    with patch.object(module, "OpenAI") as client:
        results = list(tool._invoke({"prompt": "a cat", "moderation": "invalid"}))
    assert len(results) == 1 and "moderation" in str(results[0])
    client.return_value.images.generate.assert_not_called()


@pytest.mark.parametrize("failure", ["invalid_image", "invalid_mask", "api_error"])
def test_gpt_image_edit_closes_opened_files_on_failure(failure):
    module = import_plugin_module("gpt_image_2_edit_tool", "tools/gpt_image_2_edit.py")
    tool = create_tool_instance(module.GPTImage2EditTool)
    tool.runtime.credentials = {"openai_api_key": "test-key"}
    parameters = {
        "prompt": "a cat",
        "model": "gpt-image-2.5-sunburst",
        "image": (
            [FakeFile(), "invalid"] if failure == "invalid_image" else [FakeFile(), FakeFile()]
        ),
        "mask": "invalid" if failure == "invalid_mask" else FakeFile(b"mask", "mask.png"),
    }
    opened_files = []
    bytes_io = io.BytesIO

    def track_file(blob):
        file = bytes_io(blob)
        opened_files.append(file)
        return file

    client = MagicMock()
    client.images.edit.side_effect = RuntimeError("network failed")
    with patch.object(module, "OpenAI", return_value=client), patch.object(
        module.io, "BytesIO", track_file
    ):
        results = list(tool._invoke(parameters))
    assert len(results) == 1 and isinstance(results[0], str)
    assert all(file.closed for file in opened_files)
    if failure == "api_error":
        assert len(opened_files) == 3
        assert "network failed" in results[0]
        client.images.edit.assert_called_once()
    else:
        client.images.edit.assert_not_called()
