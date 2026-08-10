"""In-process tests for Bailian Memory endpoint selection (pytest-shaped).

Fails before this change: every request went through a module-level BASE_URL
hardcoding dashscope.aliyuncs.com, so region-locked keys from the
International (Singapore) Model Studio console could never authorize."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from tools.base import BailianMemoryBaseTool  # noqa: E402


def _tool_with(credentials):
    t = BailianMemoryBaseTool()
    t.runtime = SimpleNamespace(credentials=credentials)
    return t


def test_default_is_byte_identical_cn():
    for creds in ({"dashscope_api_key": "x"},
                  {"dashscope_api_key": "x", "use_international_endpoint": "false"},
                  {"dashscope_api_key": "x", "use_international_endpoint": ""}):
        assert (_tool_with(creds)._get_base_url()
                == "https://dashscope.aliyuncs.com/api/v2/apps/memory")


def test_international_opt_in():
    t = _tool_with({"dashscope_api_key": "x", "use_international_endpoint": "true"})
    assert t._get_base_url() == "https://dashscope-intl.aliyuncs.com/api/v2/apps/memory"


def test_no_hardcoded_full_url_left():
    # the only allowed dashscope literals are the two bases + path constant in
    # base.py; no other file may carry a full dashscope URL
    for py in _PLUGIN_ROOT.rglob("*.py"):
        if "tests" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and "dashscope" in node.value and "aliyuncs.com" in node.value:
                assert py.name == "base.py", (
                    f"dashscope URL outside base.py: {py.name}:{node.lineno}")
