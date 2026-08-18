from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRIGGERS = ROOT / "triggers"

EXPECTED_MANIFEST_VERSIONS = {
    "airtable_trigger": "1.1.0",
    "github_trigger": "1.5.0",
    "gmail_trigger": "0.1.0",
    "google_calendar_trigger": "0.1.0",
    "google_drive_trigger": "1.4.0",
    "lark_trigger": "0.1.0",
    "linear_trigger": "0.6.0",
    "notion_trigger": "0.2.0",
    "outlook_trigger": "0.2.0",
    "rsshub_trigger": "0.1.0",
    "slack_trigger": "0.3.0",
    "telegram_trigger": "0.1.0",
    "twilio_trigger": "0.1.0",
    "typeform_trigger": "0.2.0",
    "woocommerce_trigger": "1.1.0",
    "zendesk_trigger": "1.1.0",
}

STORAGE_TRIGGERS = {
    "airtable_trigger",
    "github_trigger",
    "gmail_trigger",
    "google_calendar_trigger",
    "google_drive_trigger",
    "linear_trigger",
    "outlook_trigger",
    "typeform_trigger",
    "zendesk_trigger",
}

OAUTH_PROVIDERS = {
    "github_trigger": "provider/github.py",
    "gmail_trigger": "provider/gmail_trigger.py",
    "google_calendar_trigger": "provider/google_calendar_trigger.py",
    "google_drive_trigger": "provider/google_drive.py",
    "linear_trigger": "provider/linear_simple.py",
    "outlook_trigger": "provider/outlook.py",
    "typeform_trigger": "provider/typeform_simple.py",
    "zendesk_trigger": "provider/zendesk.py",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_trigger_manifest_versions_and_permissions_are_least_privilege() -> None:
    for trigger_name, expected_version in EXPECTED_MANIFEST_VERSIONS.items():
        manifest = _read(TRIGGERS / trigger_name / "manifest.yaml")

        assert re.search(rf"^version: {re.escape(expected_version)}$", manifest, re.MULTILINE), trigger_name
        assert "    model:" not in manifest
        assert "    tool:" not in manifest

        if trigger_name in STORAGE_TRIGGERS:
            assert "    storage:" in manifest, trigger_name
            assert "      enabled: true" in manifest, trigger_name
            assert "      size: 1048576" in manifest, trigger_name
        else:
            assert "  permission: {}" in manifest, trigger_name


def test_trigger_dependency_lower_bounds_are_current() -> None:
    for pyproject in TRIGGERS.glob("*/pyproject.toml"):
        text = _read(pyproject)
        assert "dify_plugin>=0.9.1" in text, pyproject
        assert "dify_plugin>=0.9.0" not in text, pyproject

    gmail = _read(TRIGGERS / "gmail_trigger" / "pyproject.toml")
    assert "google-auth>=2.55.1" in gmail
    assert "google-cloud-pubsub>=2.39.0" in gmail

    lark = _read(TRIGGERS / "lark_trigger" / "pyproject.toml")
    assert "lark-oapi>=1.6.9" in lark


def test_oauth_providers_validate_callback_state() -> None:
    for trigger_name, provider_path in OAUTH_PROVIDERS.items():
        source = _read(TRIGGERS / trigger_name / provider_path)
        assert "_store_oauth_state(redirect_uri, state)" in source, trigger_name
        assert "_validate_oauth_state(redirect_uri, request.args.get(\"state\"))" in source, trigger_name
        assert "callback missing state" in source, trigger_name


def test_google_drive_uses_compatible_token_field_and_scoped_page_tokens() -> None:
    yaml_text = _read(TRIGGERS / "google_drive_trigger" / "provider/google_drive.yaml")
    assert "- name: access_token" in yaml_text
    assert "- name: access_tokens" not in yaml_text

    source = _read(TRIGGERS / "google_drive_trigger" / "provider/google_drive.py")
    assert 'credentials.get("access_token") or credentials.get("access_tokens")' in source
    assert "_page_token_storage_key_from_key(subscription_key)" in source
    assert '"subscription_key": subscription_key' in source


def test_outlook_cleanup_removed_copied_github_logic_and_secret_storage() -> None:
    source = _read(TRIGGERS / "outlook_trigger" / "provider/outlook.py")
    assert "class OutlookSubscriptionConstructor" in source
    assert "api.github.com/user/repos" not in source
    assert "Channel.ReadBasic.All" not in source
    assert '"access_tokens": credentials.get' not in source
    assert '"refresh_token": credentials.get' not in source
    assert "_token_url(system_credentials)" in source


def test_zendesk_webhook_signatures_are_verified_when_secret_is_present() -> None:
    source = _read(TRIGGERS / "zendesk_trigger" / "provider/zendesk.py")
    assert "X-Zendesk-Webhook-Signature" in source
    assert "X-Zendesk-Webhook-Signature-Timestamp" in source
    assert "hmac.compare_digest" in source
