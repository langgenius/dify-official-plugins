import os
import yaml

PLUGIN_DIR = os.path.join('tools', 'dingo')


def test_manifest_has_required_fields():
    path = os.path.join(PLUGIN_DIR, 'manifest.yaml')
    with open(path, 'r', encoding='utf-8') as f:
        manifest = yaml.safe_load(f)
    # required top-level keys
    for key in ['author', 'name', 'type', 'label', 'description', 'icon', 'plugins', 'resource', 'tags', 'version', 'created_at']:
        assert key in manifest, f"manifest missing: {key}"
    # meta.runner
    meta = manifest.get('meta', {})
    runner = meta.get('runner', {})
    assert runner.get('language') == 'python'
    assert str(runner.get('version')).startswith('3.')
    assert runner.get('entrypoint') == 'main'


def test_provider_and_tools_exist():
    provider_yaml = os.path.join(PLUGIN_DIR, 'provider', 'dingo.yaml')
    assert os.path.exists(provider_yaml)
    with open(provider_yaml, 'r', encoding='utf-8') as f:
        provider = yaml.safe_load(f)
    # provider tools point to existing files
    tools = provider.get('tools', [])
    assert tools, 'provider.tools should not be empty'
    for rel in tools:
        tool_path = os.path.join(PLUGIN_DIR, rel)
        assert os.path.exists(tool_path), f"tool yaml missing: {tool_path}"


def test_tool_description_llm_and_human_present():
    tool_yaml = os.path.join(PLUGIN_DIR, 'tools', 'text_quality_evaluator.yaml')
    with open(tool_yaml, 'r', encoding='utf-8') as f:
        tool = yaml.safe_load(f)
    desc = tool.get('description')
    assert isinstance(desc, dict) and 'human' in desc and 'llm' in desc

