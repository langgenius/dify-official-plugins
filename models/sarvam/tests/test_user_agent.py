from pathlib import Path

import yaml

from models.llm.llm import PLUGIN_VERSION, USER_AGENT

ROOT = Path(__file__).resolve().parents[1]


def test_user_agent_matches_manifest() -> None:
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text())
    assert PLUGIN_VERSION == manifest["version"]
    assert USER_AGENT == f"dify-sarvam-plugin/{manifest['version']}"
