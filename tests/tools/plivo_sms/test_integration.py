"""
Integration tests for the Plivo SMS plugin against the real Plivo API.

Requires environment variables:
    PLIVO_AUTH_ID
    PLIVO_AUTH_TOKEN
    PLIVO_TEST_FROM_NUMBER  (E.164 format, e.g. +14155550100)
    PLIVO_TEST_TO_NUMBER    (E.164 format, e.g. +14155551234)
"""

import os
import importlib.util
import types

import pytest
from unittest.mock import MagicMock

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

PLUGIN_DIR = os.path.join("tools", "plivo_sms")

AUTH_ID = os.environ.get("PLIVO_AUTH_ID", "")
AUTH_TOKEN = os.environ.get("PLIVO_AUTH_TOKEN", "")
FROM_NUMBER = os.environ.get("PLIVO_TEST_FROM_NUMBER", "")
TO_NUMBER = os.environ.get("PLIVO_TEST_TO_NUMBER", "")

SKIP_REASON = "PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_TEST_FROM_NUMBER, and PLIVO_TEST_TO_NUMBER must be set"
has_credentials = all([AUTH_ID, AUTH_TOKEN, FROM_NUMBER, TO_NUMBER])


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def get_provider():
    mod = load_module_from_path(
        "plivo_sms_provider",
        os.path.join(PLUGIN_DIR, "provider", "plivo_sms.py"),
    )
    return mod.PlivoSmsProvider.__new__(mod.PlivoSmsProvider)


def get_tool():
    mod = load_module_from_path(
        "send_sms_tool",
        os.path.join(PLUGIN_DIR, "tools", "send_sms.py"),
    )
    tool = mod.SendSmsTool.__new__(mod.SendSmsTool)
    tool.response_type = ToolInvokeMessage
    return tool


# ── Provider credential validation ──────────────────────────────────


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


# ── Send SMS tool invocation ─────────────────────────────────────────


@pytest.mark.skipif(not has_credentials, reason=SKIP_REASON)
class TestSendSmsReal:
    def test_send_sms_success(self):
        """Send a real SMS and verify the response structure."""
        tool = get_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": AUTH_ID,
            "auth_token": AUTH_TOKEN,
        }

        results = list(tool._invoke({
            "to_number": TO_NUMBER,
            "from_number": FROM_NUMBER,
            "message": "Dify Plivo plugin integration test",
        }))

        # Should yield text message + JSON message
        assert len(results) == 2

        text_msg = results[0]
        assert text_msg.type.value == "text"
        assert "SMS sent successfully" in text_msg.message.text
        assert TO_NUMBER in text_msg.message.text
        # UUID should be present
        assert "Message UUID:" in text_msg.message.text

        json_msg = results[1]
        assert json_msg.type.value == "json"
        payload = json_msg.message.json_object
        assert payload["status"] == "success"
        assert payload["to"] == TO_NUMBER
        assert payload["from"] == FROM_NUMBER
        assert payload["message"] == "Dify Plivo plugin integration test"
        assert payload["message_uuid"]  # non-empty UUID
        assert isinstance(payload["message_uuid"], str)
        assert len(payload["message_uuid"]) > 0

    def test_send_sms_invalid_credentials(self):
        """Verify graceful error with bad credentials against real API."""
        tool = get_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": "INVALID_ID",
            "auth_token": "INVALID_TOKEN",
        }

        results = list(tool._invoke({
            "to_number": TO_NUMBER,
            "from_number": FROM_NUMBER,
            "message": "This should fail",
        }))

        assert len(results) == 1
        error_text = results[0].message.text.lower()
        assert "fail" in error_text or "error" in error_text or "authentication" in error_text

    def test_send_sms_invalid_to_number(self):
        """Verify graceful error when sending to an invalid number."""
        tool = get_tool()
        tool.runtime = MagicMock()
        tool.runtime.credentials = {
            "auth_id": AUTH_ID,
            "auth_token": AUTH_TOKEN,
        }

        results = list(tool._invoke({
            "to_number": "0000",
            "from_number": FROM_NUMBER,
            "message": "This should fail",
        }))

        # Should get an error message, not crash
        assert len(results) >= 1
        # The response should indicate an error
        result_text = str(results[0]).lower()
        assert any(word in result_text for word in ["error", "invalid", "fail"])
