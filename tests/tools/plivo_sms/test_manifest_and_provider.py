import os

import yaml

PLUGIN_DIR = os.path.join("tools", "plivo_sms")


def test_manifest_has_required_fields():
    path = os.path.join(PLUGIN_DIR, "manifest.yaml")
    with open(path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    for key in [
        "author",
        "name",
        "type",
        "label",
        "description",
        "icon",
        "plugins",
        "resource",
        "tags",
        "version",
        "created_at",
    ]:
        assert key in manifest, f"manifest missing: {key}"
    meta = manifest.get("meta", {})
    runner = meta.get("runner", {})
    assert runner.get("language") == "python"
    assert str(runner.get("version")).startswith("3.")
    assert runner.get("entrypoint") == "main"


def test_manifest_type_is_plugin():
    path = os.path.join(PLUGIN_DIR, "manifest.yaml")
    with open(path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    assert manifest["type"] == "plugin"


def test_manifest_plugins_references_provider_yaml():
    path = os.path.join(PLUGIN_DIR, "manifest.yaml")
    with open(path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    tools = manifest.get("plugins", {}).get("tools", [])
    assert tools, "manifest.plugins.tools should not be empty"
    for rel in tools:
        provider_path = os.path.join(PLUGIN_DIR, rel)
        assert os.path.exists(provider_path), f"provider yaml missing: {provider_path}"


def test_provider_yaml_has_credentials_and_tools():
    provider_yaml = os.path.join(PLUGIN_DIR, "provider", "plivo_sms.yaml")
    with open(provider_yaml, "r", encoding="utf-8") as f:
        provider = yaml.safe_load(f)
    # Must have credentials
    creds = provider.get("credentials_for_provider", {})
    assert "auth_id" in creds, "missing auth_id credential"
    assert "auth_token" in creds, "missing auth_token credential"
    # Must reference tools
    tools = provider.get("tools", [])
    assert tools, "provider.tools should not be empty"
    for rel in tools:
        tool_path = os.path.join(PLUGIN_DIR, rel)
        assert os.path.exists(tool_path), f"tool yaml missing: {tool_path}"


def test_provider_yaml_has_extra_python_source():
    provider_yaml = os.path.join(PLUGIN_DIR, "provider", "plivo_sms.yaml")
    with open(provider_yaml, "r", encoding="utf-8") as f:
        provider = yaml.safe_load(f)
    source = provider.get("extra", {}).get("python", {}).get("source")
    assert source, "provider must have extra.python.source"
    source_path = os.path.join(PLUGIN_DIR, source)
    assert os.path.exists(source_path), f"provider source missing: {source_path}"


def test_tool_yaml_has_required_fields():
    tool_yaml = os.path.join(PLUGIN_DIR, "tools", "send_sms.yaml")
    with open(tool_yaml, "r", encoding="utf-8") as f:
        tool = yaml.safe_load(f)
    # identity
    identity = tool.get("identity", {})
    assert identity.get("name") == "send_sms"
    assert "label" in identity
    # description
    desc = tool.get("description", {})
    assert "human" in desc, "tool missing human description"
    assert "llm" in desc, "tool missing llm description"
    # parameters
    params = tool.get("parameters", [])
    param_names = {p["name"] for p in params}
    assert "to_number" in param_names
    assert "from_number" in param_names
    assert "message" in param_names
    # extra.python.source
    source = tool.get("extra", {}).get("python", {}).get("source")
    assert source, "tool must have extra.python.source"
    source_path = os.path.join(PLUGIN_DIR, source)
    assert os.path.exists(source_path), f"tool source missing: {source_path}"


def test_icon_exists():
    icon_path = os.path.join(PLUGIN_DIR, "_assets", "icon.svg")
    assert os.path.exists(icon_path), "icon.svg missing"
