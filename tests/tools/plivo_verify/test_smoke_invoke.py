import os
import importlib.util
import types
from unittest.mock import MagicMock, patch

from dify_plugin.entities.tool import ToolInvokeMessage

PLUGIN_DIR = os.path.join("tools", "plivo_verify")


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader, f"cannot load spec for {module_name} from {file_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def create_send_otp_tool_instance(mod):
    """Create a SendOtpTool with response_type set so create_text/json_message work."""
    tool = mod.SendOtpTool.__new__(mod.SendOtpTool)
    tool.response_type = ToolInvokeMessage
    return tool


def create_verify_otp_tool_instance(mod):
    """Create a VerifyOtpTool with response_type set so create_text/json_message work."""
    tool = mod.VerifyOtpTool.__new__(mod.VerifyOtpTool)
    tool.response_type = ToolInvokeMessage
    return tool


def test_provider_python_loadable():
    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_verify.py")
    mod = load_module_from_path("plivo_verify_provider", provider_py)
    assert hasattr(mod, "PlivoVerifyProvider")


def test_send_otp_tool_python_loadable_and_has_invoke():
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool_cls = getattr(mod, "SendOtpTool")
    assert callable(getattr(tool_cls, "_invoke"))


def test_verify_otp_tool_python_loadable_and_has_invoke():
    tool_py = os.path.join(PLUGIN_DIR, "tools", "verify_otp.py")
    mod = load_module_from_path("verify_otp_tool", tool_py)
    tool_cls = getattr(mod, "VerifyOtpTool")
    assert callable(getattr(tool_cls, "_invoke"))


def test_provider_validate_credentials_success():
    """Test that valid credentials pass validation via mocked Plivo API."""
    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_verify.py")
    mod = load_module_from_path("plivo_verify_provider", provider_py)
    provider = mod.PlivoVerifyProvider.__new__(mod.PlivoVerifyProvider)

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

    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_verify.py")
    mod = load_module_from_path("plivo_verify_provider", provider_py)
    provider = mod.PlivoVerifyProvider.__new__(mod.PlivoVerifyProvider)

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

    provider_py = os.path.join(PLUGIN_DIR, "provider", "plivo_verify.py")
    mod = load_module_from_path("plivo_verify_provider", provider_py)
    provider = mod.PlivoVerifyProvider.__new__(mod.PlivoVerifyProvider)

    with pytest.raises(ToolProviderCredentialValidationError):
        provider._validate_credentials({"auth_id": "ONLY_ID"})


def test_send_otp_tool_invoke_success():
    """Test send_otp tool returns success messages via mocked Plivo API."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    # Mock runtime.credentials
    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_AUTH_ID",
        "auth_token": "TEST_AUTH_TOKEN",
    }

    mock_response = MagicMock()
    mock_response.session_uuid = "test-session-uuid-12345"

    mock_client = MagicMock()
    mock_client.verify_session.create.return_value = mock_response

    with patch("plivo.RestClient", return_value=mock_client) as mock_rest:
        results = list(tool._invoke({
            "phone_number": "+14155551234",
            "channel": "sms",
        }))

        mock_rest.assert_called_once_with(auth_id="TEST_AUTH_ID", auth_token="TEST_AUTH_TOKEN")
        mock_client.verify_session.create.assert_called_once_with(
            recipient="+14155551234",
            channel="sms",
        )

    # Should yield 2 messages: text + json
    assert len(results) == 2

    text_msg = results[0]
    assert "test-session-uuid-12345" in str(text_msg)

    json_msg = results[1]
    assert "test-session-uuid-12345" in str(json_msg)


def test_send_otp_tool_invoke_default_channel():
    """Test send_otp tool uses sms channel by default."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_AUTH_ID",
        "auth_token": "TEST_AUTH_TOKEN",
    }

    mock_response = MagicMock()
    mock_response.session_uuid = "test-session-uuid"

    mock_client = MagicMock()
    mock_client.verify_session.create.return_value = mock_response

    with patch("plivo.RestClient", return_value=mock_client):
        # Don't pass channel parameter
        results = list(tool._invoke({
            "phone_number": "+14155551234",
        }))

        mock_client.verify_session.create.assert_called_once_with(
            recipient="+14155551234",
            channel="sms",
        )


def test_send_otp_tool_invoke_voice_channel():
    """Test send_otp tool with voice channel."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_AUTH_ID",
        "auth_token": "TEST_AUTH_TOKEN",
    }

    mock_response = MagicMock()
    mock_response.session_uuid = "test-session-uuid"

    mock_client = MagicMock()
    mock_client.verify_session.create.return_value = mock_response

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "phone_number": "+14155551234",
            "channel": "voice",
        }))

        mock_client.verify_session.create.assert_called_once_with(
            recipient="+14155551234",
            channel="voice",
        )


def test_send_otp_tool_invoke_with_app_uuid():
    """Test send_otp tool with custom app_uuid."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_AUTH_ID",
        "auth_token": "TEST_AUTH_TOKEN",
    }

    mock_response = MagicMock()
    mock_response.session_uuid = "test-session-uuid"

    mock_client = MagicMock()
    mock_client.verify_session.create.return_value = mock_response

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "phone_number": "+14155551234",
            "channel": "sms",
            "app_uuid": "custom-app-uuid-12345",
        }))

        mock_client.verify_session.create.assert_called_once_with(
            recipient="+14155551234",
            channel="sms",
            app_uuid="custom-app-uuid-12345",
        )


def test_send_otp_tool_invoke_auth_failure():
    """Test send_otp tool handles auth failure gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "BAD_ID",
        "auth_token": "BAD_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.create.side_effect = plivo.exceptions.AuthenticationError("unauthorized")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "phone_number": "+14155551234",
        }))

    assert len(results) == 1
    assert "authentication failed" in str(results[0]).lower()


def test_send_otp_tool_invoke_validation_error():
    """Test send_otp tool handles Plivo validation errors gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.create.side_effect = plivo.exceptions.ValidationError("invalid number")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "phone_number": "not-a-number",
        }))

    assert len(results) == 1
    assert "invalid" in str(results[0]).lower()


def test_send_otp_tool_invoke_api_error():
    """Test send_otp tool handles Plivo REST API errors gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "send_otp.py")
    mod = load_module_from_path("send_otp_tool", tool_py)
    tool = create_send_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.create.side_effect = plivo.exceptions.PlivoRestError("server error")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "phone_number": "+14155551234",
        }))

    assert len(results) == 1
    assert "plivo api error" in str(results[0]).lower()


def test_verify_otp_tool_invoke_success():
    """Test verify_otp tool returns success messages via mocked Plivo API."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "verify_otp.py")
    mod = load_module_from_path("verify_otp_tool", tool_py)
    tool = create_verify_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_AUTH_ID",
        "auth_token": "TEST_AUTH_TOKEN",
    }

    mock_response = MagicMock()

    mock_client = MagicMock()
    mock_client.verify_session.validate.return_value = mock_response

    with patch("plivo.RestClient", return_value=mock_client) as mock_rest:
        results = list(tool._invoke({
            "session_id": "test-session-uuid-12345",
            "otp_code": "123456",
        }))

        mock_rest.assert_called_once_with(auth_id="TEST_AUTH_ID", auth_token="TEST_AUTH_TOKEN")
        mock_client.verify_session.validate.assert_called_once_with(
            session_uuid="test-session-uuid-12345",
            otp="123456",
        )

    # Should yield 2 messages: text + json
    assert len(results) == 2

    text_msg = results[0]
    assert "verified successfully" in str(text_msg).lower()

    json_msg = results[1]
    assert "success" in str(json_msg)


def test_verify_otp_tool_invoke_auth_failure():
    """Test verify_otp tool handles auth failure gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "verify_otp.py")
    mod = load_module_from_path("verify_otp_tool", tool_py)
    tool = create_verify_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "BAD_ID",
        "auth_token": "BAD_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.validate.side_effect = plivo.exceptions.AuthenticationError("unauthorized")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "session_id": "test-session-uuid",
            "otp_code": "123456",
        }))

    assert len(results) == 1
    assert "authentication failed" in str(results[0]).lower()


def test_verify_otp_tool_invoke_invalid_otp():
    """Test verify_otp tool handles invalid OTP gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "verify_otp.py")
    mod = load_module_from_path("verify_otp_tool", tool_py)
    tool = create_verify_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.validate.side_effect = plivo.exceptions.ValidationError("invalid OTP")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "session_id": "test-session-uuid",
            "otp_code": "000000",
        }))

    # Should return 2 messages: text error + json with verified=false
    assert len(results) == 2
    assert "failed" in str(results[0]).lower()
    assert "verified" in str(results[1]).lower()


def test_verify_otp_tool_invoke_expired_session():
    """Test verify_otp tool handles expired session gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "verify_otp.py")
    mod = load_module_from_path("verify_otp_tool", tool_py)
    tool = create_verify_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.validate.side_effect = plivo.exceptions.PlivoRestError("session expired")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "session_id": "expired-session-uuid",
            "otp_code": "123456",
        }))

    # Should return verification failure
    assert len(results) == 2
    assert "failed" in str(results[0]).lower()


def test_verify_otp_tool_invoke_api_error():
    """Test verify_otp tool handles Plivo REST API errors gracefully."""
    import plivo

    tool_py = os.path.join(PLUGIN_DIR, "tools", "verify_otp.py")
    mod = load_module_from_path("verify_otp_tool", tool_py)
    tool = create_verify_otp_tool_instance(mod)

    tool.runtime = MagicMock()
    tool.runtime.credentials = {
        "auth_id": "TEST_ID",
        "auth_token": "TEST_TOKEN",
    }

    mock_client = MagicMock()
    mock_client.verify_session.validate.side_effect = plivo.exceptions.PlivoRestError("server error")

    with patch("plivo.RestClient", return_value=mock_client):
        results = list(tool._invoke({
            "session_id": "test-session-uuid",
            "otp_code": "123456",
        }))

    assert len(results) == 1
    assert "plivo api error" in str(results[0]).lower()
