"""The plugin loader's rules, which only bite at install time in a real Dify.

``PluginRegistration`` calls ``load_single_subclass_from_source`` on every file named by a
tool YAML and refuses the plugin outright if a file contains more or less than exactly one
``Tool`` subclass. An imported shared base class counts towards that total, which is why the
shared behaviour lives in a plain mixin. Nothing in a normal unit test exercises this, so it
is asserted here directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("dify_plugin", reason="the Dify SDK is only installed in the plugin runtime")

from dify_plugin import Tool  # noqa: E402
from dify_plugin.core.utils.class_loader import load_single_subclass_from_source  # noqa: E402


def tool_sources() -> list[Path]:
    provider = yaml.safe_load((ROOT / "provider" / "aihubmix-image.yaml").read_text())
    sources = []
    for tool_yaml in provider["tools"]:
        spec = yaml.safe_load((ROOT / tool_yaml).read_text())
        sources.append(ROOT / spec["extra"]["python"]["source"])
    return sources


def test_every_declared_tool_source_exists():
    sources = tool_sources()
    assert sources
    for source in sources:
        assert source.is_file(), source


@pytest.mark.parametrize("source", tool_sources(), ids=lambda p: p.name)
def test_each_tool_file_exposes_exactly_one_tool_subclass(source: Path):
    # Raises "Multiple subclasses of Tool" if a shared base is imported as a Tool subclass.
    tool_cls = load_single_subclass_from_source(
        module_name=f"tests.{source.stem}", script_path=str(source), parent_type=Tool
    )
    assert issubclass(tool_cls, Tool)
    # The mixin must come first so its fetch_parameter_options beats the SDK's default.
    assert tool_cls.fetch_parameter_options is not Tool.fetch_parameter_options
