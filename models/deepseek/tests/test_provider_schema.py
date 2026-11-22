"""Schema checks for the opt-in provider credentials in `provider/deepseek.yaml`.

The plugin decisions (forward `user_id`, attach Dify headers) read these
credentials at runtime. A typo in the YAML (`default`, option value, variable
name) would silently make an opt-in unreachable, so the shape is asserted here
instead of relying on a manual look at the file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _credentials() -> dict[str, dict]:
    schema = yaml.safe_load((PLUGIN_ROOT / "provider" / "deepseek.yaml").read_text("utf-8"))
    items = schema["provider_credential_schema"]["credential_form_schemas"]
    return {item["variable"]: item for item in items}


def test_user_id_switch_defaults_to_disabled() -> None:
    credential = _credentials()["enable_user_id"]

    assert credential["type"] == "select"
    assert credential["required"] is False
    assert credential["default"] == "disabled"
    values = {option["value"] for option in credential["options"]}
    assert values == {"enabled", "disabled"}


def test_request_metadata_switch_keeps_its_contract() -> None:
    credential = _credentials()["enable_request_metadata"]

    assert credential["type"] == "select"
    assert credential["default"] == "disabled"
    values = {option["value"] for option in credential["options"]}
    assert values == {"enabled", "disabled"}


def test_api_key_is_still_required() -> None:
    credential = _credentials()["api_key"]

    assert credential["type"] == "secret-input"
    assert credential["required"] is True
