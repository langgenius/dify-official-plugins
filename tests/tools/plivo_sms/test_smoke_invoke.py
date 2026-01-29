import os
import importlib.util
import types
from unittest.mock import MagicMock, patch

from dify_plugin.entities.tool import ToolInvokeMessage

PLUGIN_DIR = os.path.join("tools", "plivo_sms")


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader, f"cannot load spec for {module_name} from {file_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def create_tool_instance(mod):
    """Create a SendSmsTool with response_type set so create_text/json_message work."""
    tool = mod.SendSmsTool.__new__(mod.SendSmsTool)
    tool.response_type = ToolInvokeMessage
    return tool


def test_provider_python_loadable():
    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_sms.py")
    mod = load_module_from_path("plivo_sms_provider", provider_py)
    assert hasattr(mod, "PlivoSmsProvider")


def test_tool_python_loadable_and_has_invoke():
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_sms.py")
    mod = load_module_from_path("send_sms_tool", tool_py)
    tool_cls = getattr(mod, "SendSmsTool")
    assert callable(getattr(tool_cls, "_invoke"))


def test_provider_validate_credentials_success():
    """Test that valid credentials pass validation via mocked Plivo API."""
    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_sms.py")
    mod = load_module_from_path("plivo_sms_provider", provider_py)
    provider = mod.PlivoSmsProvider.__new__(mod.PlivoSmsProvider)

    mock_client = MagicMock()
    mock_client.account.get.return_value = {"status": "active"}

    with patch("plivo.RestClient", return_value=mock_client) as mock_rest:
        provider._validate_credentials({
            "auth_id": "TEST_AUTH_ID",
            "auth_token": "TEST_AUTH_TOKEN",
        })
        mock_rest.assert_called_once_with(auth_id="TEST_AUTH_ID", auth_token="TEST_AUTH_TOKEN")
        mock_client.account.get.assert_called_once()


def test_provider_validate_credentials_invalid():
    """Test that invalid credentials raise ToolProviderCredentialValidationError."""
    import plivo
    import pytest
    from dify_plugin.errors.tool import ToolProviderCredentialValidationError

    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_sms.py")
    mod = load_module_from_path("plivo_sms_provider", provider_py)
    provider = mod.PlivoSmsProvider.__new__(mod.PlivoSmsProvider)

    mock_client = MagicMock()
    mock_client.account.get.side_effect = plivo.exceptions.AuthenticationError("bad creds")

    with patch("plivo.RestClient", return_value=mock_client):
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "auth_id": "BAD_ID",
                "auth_token": "BAD_TOKEN",
            })


def test_provider_validate_credentials_missing_key():
    """Test that missing credentials raise ToolProviderCredentialValidationError."""
    import pytest
    from dify_plugin.errors.tool import ToolProviderCredentialValidationError

    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_sms.py")
    mod = load_module_from_path("plivo_sms_provider", provider_py)
    provider = mod.PlivoSmsProvider.__new__(mod.PlivoSmsProvider)

    with pytest.raises(ToolProviderCredentialValidationError):
        provider._validate_credentials({"auth_id": "ONLY_ID"})


def test_send_sms_tool_invoke_success():
    """Test send_sms tool returns success messages via mocked Plivo API."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_sms.py")
    mod = load_module_from_path("send_sms_tool", tool_py)
    tool = create_tool_instance(mod)

    # Mock runtime.credentials
    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_AUTH_ID",
        "auth_token": "TEST_AUTH_TOKEN",
    }

    mock_response = MagicMock()
    mock_response.message_uuid = ["test-uuid-12345"]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("plivo.RestClient", return_value=mock_client) as mock_rest:
        results = list(tool._invoke({
            "to_number": "+14155551234",
            "from_number": "+14155550100",
            "message": "Hello from Dify!",
        }))

        mock_rest.assert_called_once_with(auth_id="TEST_AUTH_ID", auth_token="TEST_AUTH_TOKEN")
        mock_client.messages.create.assert_called_once_with(
            src="+14155550100",
            dst="+14155551234",
            text="Hello from Dify!",
        )

    # Should yield 2 messages: text + json
    assert len(results) == 2

    text_msg = results[0]
    assert "test-uuid-12345" in str(text_msg)

    json_msg = results[1]
    assert "test-uuid-12345" in str(json_msg)


def test_send_sms_tool_invoke_auth_failure():
    """Test send_sms tool handles auth failure gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_sms.py")
    mod = load_module_from_path("send_sms_tool", tool_py)
    tool = create_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "BAD_ID",
        "auth_token": "BAD_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = plivo.exceptions.AuthenticationError("unauthorized")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "to_number": "+14155551234",
            "from_number": "+14155550100",
            "message": "Hello",
        }))

    assert len(results) == 1
    assert "authentication failed" in str(results[0]).lower()


def test_send_sms_tool_invoke_validation_error():
    """Test send_sms tool handles Plivo validation errors gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_sms.py")
    mod = load_module_from_path("send_sms_tool", tool_py)
    tool = create_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = plivo.exceptions.ValidationError("invalid number")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "to_number": "not-a-number",
            "from_number": "+14155550100",
            "message": "Hello",
        }))

    assert len(results) == 1
    assert "invalid" in str(results[0]).lower()


def test_send_sms_tool_invoke_api_error():
    """Test send_sms tool handles Plivo REST API errors gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_sms.py")
    mod = load_module_from_path("send_sms_tool", tool_py)
    tool = create_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = plivo.exceptions.PlivoRestError("server error")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "to_number": "+14155551234",
            "from_number": "+14155550100",
            "message": "Hello",
        }))

    assert len(results) == 1
    assert "plivo api error" in str(results[0]).lower()
