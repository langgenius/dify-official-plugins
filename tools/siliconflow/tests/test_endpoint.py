"""In-process tests for the SiliconFlow endpoint selection (pytest-shaped).

Fails before this change: every API call hardcoded api.siliconflow.cn, so an
international (api.siliconflow.com) key could never validate or invoke."""

from __future__ import annotations

import dify_plugin  # noqa: F401  (gevent-patches ssl; must precede requests)

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from utils.endpoint import get_base_url  # noqa: E402


def test_default_is_byte_identical_cn():
    # absent, "false", and empty-string credential all resolve to the exact
    # host every existing installation used before this change
    for creds in ({}, {"use_international_endpoint": "false"},
                  {"use_international_endpoint": ""}):
        assert get_base_url(creds) == "https://api.siliconflow.cn"


def test_international_opt_in():
    assert (
        get_base_url({"use_international_endpoint": "true"})
        == "https://api.siliconflow.com"
    )


def test_no_hardcoded_host_left_in_api_calls():
    # no string literal in provider/ or tools/ may carry a full
    # https://api.siliconflow URL — the helper in utils/endpoint.py is the
    # single source of the host (host names in human-readable error text,
    # without a scheme, are fine)
    import ast

    for sub in ("provider", "tools"):
        for py in (_PLUGIN_ROOT / sub).glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert not node.value.startswith("https://api.siliconflow"), (
                        f"hardcoded API host in {py.name}:{node.lineno}: "
                        f"{node.value!r}"
                    )


def test_validation_401_names_the_endpoint_it_hit():
    """Unmocked, real-network: both SiliconFlow hosts return 401 for a junk
    key, so the validation error must name the base URL that rejected it.
    Asserts provider validation flows through the endpoint switch."""
    import pytest

    from dify_plugin.errors.tool import ToolProviderCredentialValidationError
    from provider.siliconflow import SiliconflowProvider

    provider = SiliconflowProvider.__new__(SiliconflowProvider)
    for flag, host in (
        ("true", "api.siliconflow.com"),
        ("false", "api.siliconflow.cn"),
    ):
        credentials = {
            "siliconFlow_api_key": "sk-invalid-on-purpose",
            "use_international_endpoint": flag,
        }
        with pytest.raises(ToolProviderCredentialValidationError) as excinfo:
            provider._validate_credentials(credentials)
        assert host in str(excinfo.value), (
            f"validation error must name {host}: {excinfo.value}"
        )
