"""
Integration tests for the Plivo Verify plugin against the real Plivo API.

Requires environment variables:
    PLIVO_AUTH_ID
    PLIVO_AUTH_TOKEN
    PLIVO_TEST_TO_NUMBER    (E.164 format, e.g. +14155551234)

Note: These tests will send real OTP codes and incur charges on your Plivo account.
The verify step requires manual OTP entry, so full verification flow tests are
marked for manual execution only.
"""

import os
import importlib.util
import types

import pytest
from unittest.mock import MagicMock

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

PLUGIN_DIR = os.path.join("tools", "plivo_verify")

AUTH_ID = os.environ.get("PLIVO_AUTH_ID", "")
AUTH_TOKEN = os.environ.get("PLIVO_AUTH_TOKEN", "")
TO_NUMBER = os.environ.get("PLIVO_TEST_TO_NUMBER", "")

SKIP_REASON = "PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, and PLIVO_TEST_TO_NUMBER must be set"
has_credentials = all([AUTH_ID, AUTH_TOKEN, TO_NUMBER])


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def get_provider():
    mod = load_module_from_path(
        "plivo_verify_provider",
        os.path.join(PLUGIN_DIR, "provider", "plivo_verify.py"),
    )
    return mod.PlivoVerifyProvider.__new__(mod.PlivoVerifyProvider)


def get_send_otp_tool():
    mod = load_module_from_path(
        "send_otp_tool",
        os.path.join(PLUGIN_DIR, "tools", "send_otp.py"),
    )
    tool = mod.SendOtpTool.__new__(mod.SendOtpTool)
    tool.response_type = ToolInvokeMessage
    return tool


def get_verify_otp_tool():
    mod = load_module_from_path(
        "verify_otp_tool",
        os.path.join(PLUGIN_DIR, "tools", "verify_otp.py"),
    )
    tool = mod.VerifyOtpTool.__new__(mod.VerifyOtpTool)
    tool.response_type = ToolInvokeMessage
    return tool


# -- Provider credential validation ------------------------------------------


@pytest.mark.skipif(not has_credentials, reason=SKIP_REASON)
class TestProviderCredentialsReal:
    def test_valid_credentials(self):
        provider = get_provider()
        # Should not raise
        provider._validate_credentials({
            "auth_id": AUTH_ID,
            "auth_token": AUTH_TOKEN,
        })

    def test_invalid_auth_token(self):
        provider = get_provider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "auth_id": AUTH_ID,
                "auth_token": "DEFINITELY_INVALID_TOKEN",
            })

    def test_invalid_auth_id(self):
        provider = get_provider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({
                "auth_id": "INVALID_ID_12345",
                "auth_token": AUTH_TOKEN,
            })

    def test_empty_credentials(self):
        provider = get_provider()
        with pytest.raises(ToolProviderCredentialValidationError):
            provider._validate_credentials({})


# -- Send OTP tool invocation ------------------------------------------------


@pytest.mark.skipif(not has_credentials, reason=SKIP_REASON)
class TestSendOtpReal:
    def test_send_otp_success_sms(self):
        """Send a real OTP via SMS and verify the response structure."""
        tool = get_send_otp_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": AUTH_ID,
            "auth_token": AUTH_TOKEN,
        }

        results = list(tool._invoke({
            "phone_number": TO_NUMBER,
            "channel": "sms",
        }))

        # Should yield text message + JSON message
        assert len(results) == 2

        text_msg = results[0]
        assert text_msg.type.value == "text"
        assert "OTP sent successfully" in text_msg.message.text
        assert TO_NUMBER in text_msg.message.text
        assert "Session ID:" in text_msg.message.text

        json_msg = results[1]
        assert json_msg.type.value == "json"
        payload = json_msg.message.json_object
        assert payload["status"] == "success"
        assert payload["phone_number"] == TO_NUMBER
        assert payload["channel"] == "sms"
        assert payload["session_id"]  # non-empty UUID
        assert isinstance(payload["session_id"], str)
        assert len(payload["session_id"]) > 0

    def test_send_otp_invalid_credentials(self):
        """Verify graceful error with bad credentials against real API."""
        tool = get_send_otp_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": "INVALID_ID",
            "auth_token": "INVALID_TOKEN",
        }

        results = list(tool._invoke({
            "phone_number": TO_NUMBER,
            "channel": "sms",
        }))

        assert len(results) == 1
        error_text = results[0].message.text.lower()
        assert "fail" in error_text or "error" in error_text or "authentication" in error_text

    def test_send_otp_invalid_phone_number(self):
        """Verify graceful error when sending to an invalid number."""
        tool = get_send_otp_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": AUTH_ID,
            "auth_token": AUTH_TOKEN,
        }

        results = list(tool._invoke({
            "phone_number": "0000",
            "channel": "sms",
        }))

        # Should get an error message, not crash
        assert len(results) >= 1
        # The response should indicate an error
        result_text = results[0].message.text.lower()
        assert any(word in result_text for word in ["error", "invalid", "fail"])


# -- Verify OTP tool invocation ----------------------------------------------


@pytest.mark.skipif(not has_credentials, reason=SKIP_REASON)
class TestVerifyOtpReal:
    def test_verify_otp_invalid_credentials(self):
        """Verify graceful error with bad credentials against real API."""
        tool = get_verify_otp_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": "INVALID_ID",
            "auth_token": "INVALID_TOKEN",
        }

        results = list(tool._invoke({
            "session_id": "fake-session-uuid",
            "otp_code": "123456",
        }))

        assert len(results) == 1
        error_text = results[0].message.text.lower()
        assert "fail" in error_text or "error" in error_text or "authentication" in error_text

    def test_verify_otp_invalid_session(self):
        """Verify graceful error when using an invalid session ID."""
        tool = get_verify_otp_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": AUTH_ID,
            "auth_token": AUTH_TOKEN,
        }

        results = list(tool._invoke({
            "session_id": "00000000-0000-0000-0000-000000000000",
            "otp_code": "123456",
        }))

        # Should get an error message, not crash
        assert len(results) >= 1
        # The response should indicate an error or verification failure
        result_text = results[0].message.text.lower()
        assert any(word in result_text for word in ["error", "invalid", "fail", "not found"])
