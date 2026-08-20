"""In-process tests for StepFun endpoint selection (pytest-shaped).

Fails before this change: _add_custom_parameters unconditionally hardcoded
https://api.stepfun.com/v1, so keys minted on the international platform
(platform.stepfun.ai) could never validate or invoke."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent

_LLM_PY = _PLUGIN_ROOT / "models" / "llm" / "llm.py"


def _add_custom_parameters(credentials):
    """The switch under test, extracted by AST so the test needs no SDK
    install: executes the real _add_custom_parameters body."""
    tree = ast.parse(_LLM_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_add_custom_parameters":
            fn = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(fn, str(_LLM_PY), "exec"), ns)  # noqa: S102
            ns["_add_custom_parameters"](None, credentials)
            return credentials
    raise AssertionError("_add_custom_parameters not found")


def test_default_is_byte_identical_com():
    for creds in ({}, {"use_international_endpoint": "false"},
                  {"use_international_endpoint": ""}):
        out = _add_custom_parameters(dict(creds))
        assert out["endpoint_url"] == "https://api.stepfun.com/v1"
        assert out["mode"] == "chat"


def test_international_opt_in():
    out = _add_custom_parameters({"use_international_endpoint": "true"})
    assert out["endpoint_url"] == "https://api.stepfun.ai/v1"


def test_radio_offered_in_both_credential_schemas():
    text = (_PLUGIN_ROOT / "provider" / "stepfun.yaml").read_text(encoding="utf-8")
    assert text.count("variable: use_international_endpoint") == 2, (
        "the endpoint radio must exist in BOTH provider_credential_schema and "
        "model_credential_schema, or customizable models stay .com-only"
    )


def test_validation_401_names_the_endpoint_it_hit():
    """Unmocked, real-network: proves validate_credentials itself flows through
    the endpoint switch, and that the failure names the host that rejected the
    key. Both StepFun hosts return byte-identical 401 bodies for a bad key, so
    without the endpoint in the message a wrong-region 401 is undiagnosable
    (2026-08-10 lesson: a monkeypatched dependency is an untested dependency)."""
    import dify_plugin  # noqa: F401  (gevent-patches ssl; must precede requests)
    import pytest

    sys.path.insert(0, str(_PLUGIN_ROOT))
    from dify_plugin.errors.model import CredentialsValidateFailedError
    from models.llm.llm import StepfunLargeLanguageModel

    model = StepfunLargeLanguageModel([])
    for flag, host in (("true", "api.stepfun.ai"), ("false", "api.stepfun.com")):
        credentials = {
            "api_key": "sk-invalid-on-purpose",
            "use_international_endpoint": flag,
        }
        with pytest.raises(CredentialsValidateFailedError) as excinfo:
            model.validate_credentials("step-3.7-flash", credentials)
        assert host in str(excinfo.value), (
            f"validation error must name {host}: {excinfo.value}"
        )
        assert credentials["endpoint_url"] == f"https://{host}/v1"
