#!/usr/bin/env python3
"""
Manual test for the full OTP verification flow.

This script sends a real OTP and prompts you to enter the code received via SMS.

Usage:
    PLIVO_AUTH_ID=xxx PLIVO_AUTH_TOKEN=xxx PLIVO_TEST_TO_NUMBER=+1... \
        python tests/tools/plivo_verify/test_manual_full_flow.py
"""

import os
import sys
import importlib.util
import types
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from dify_plugin.entities.tool import ToolInvokeMessage

PLUGIN_DIR = os.path.join("tools", "plivo_verify")

AUTH_ID = os.environ.get("PLIVO_AUTH_ID", "")
AUTH_TOKEN = os.environ.get("PLIVO_AUTH_TOKEN", "")
TO_NUMBER = os.environ.get("PLIVO_TEST_TO_NUMBER", "")


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def main():
    if not all([AUTH_ID, AUTH_TOKEN, TO_NUMBER]):
        print("Error: PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, and PLIVO_TEST_TO_NUMBER must be set")
        sys.exit(1)

    print(f"=== Plivo Verify Full Flow Test ===\n")
    print(f"Sending OTP to: {TO_NUMBER}")
    print(f"Channel: sms\n")

    # Step 1: Send OTP
    send_tool = get_send_otp_tool()
    send_tool.runtime = MagicMock()
    send_tool.runtime.credentials = {
        "auth_id": AUTH_ID,
        "auth_token": AUTH_TOKEN,
    }

    results = list(send_tool._invoke({
        "phone_number": TO_NUMBER,
        "channel": "sms",
    }))

    # Check if send was successful
    if len(results) < 2:
        print(f"Send OTP failed: {results[0].message.text}")
        sys.exit(1)

    json_result = results[1].message.json_object
    if json_result.get("status") != "success":
        print(f"Send OTP failed: {results[0].message.text}")
        sys.exit(1)

    session_id = json_result["session_id"]
    print(f"OTP sent successfully!")
    print(f"Session ID: {session_id}\n")

    # Step 2: Get OTP from user
    print("-" * 40)
    otp_code = input("Enter the OTP code you received via SMS: ").strip()
    print("-" * 40)
    print()

    if not otp_code:
        print("No OTP entered. Exiting.")
        sys.exit(1)

    # Step 3: Verify OTP
    print(f"Verifying OTP: {otp_code}")
    print(f"Session ID: {session_id}\n")

    verify_tool = get_verify_otp_tool()
    verify_tool.runtime = MagicMock()
    verify_tool.runtime.credentials = {
        "auth_id": AUTH_ID,
        "auth_token": AUTH_TOKEN,
    }

    results = list(verify_tool._invoke({
        "session_id": session_id,
        "otp_code": otp_code,
    }))

    # Display results
    print("=== Verification Result ===\n")
    for result in results:
        if hasattr(result.message, 'text'):
            print(f"Text: {result.message.text}")
        if hasattr(result.message, 'json_object'):
            print(f"JSON: {result.message.json_object}")
    print()

    # Check verification status
    if len(results) >= 2:
        json_result = results[1].message.json_object
        if json_result.get("verified") is True:
            print("SUCCESS: Phone number verified!")
            sys.exit(0)
        else:
            print(f"FAILED: Verification unsuccessful")
            sys.exit(1)
    else:
        # Single result usually means an error
        print(f"FAILED: {results[0].message.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
