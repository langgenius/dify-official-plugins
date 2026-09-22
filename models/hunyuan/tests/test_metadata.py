"""Unit tests for the opt-in Dify metadata helper used by the Hunyuan plugin.

The helper writes Dify `X-Dify-App-Id` and `X-Dify-Source: dify` headers into
`credentials['extra_headers']` when the credential `enable_request_metadata` is
`"enabled"` and a Dify `app_id` resolves. The Hunyuan plugin then reads
`credentials.get("extra_headers", {})` and assigns the dict onto
`request.headers` on each `ChatCompletionsRequest`. The Tencent SDK's
`HunyuanClient.ChatCompletions` forwards `request.headers` to its
`_call_and_deserialize(..., headers=request.headers)` method, which sends
them on the outbound HTTP call.

When the credential is disabled, or `app_id` is missing / empty, the helper
does nothing and the request shape is unchanged.

These tests do not need a network or the Tencent SDK: the helper is pure and
runs entirely in memory. The integration with `_setup_hunyuan_client` and the
two `client.ChatCompletions(request)` call sites is verified by the
source-level guard tests at the bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm._metadata import (  # noqa: E402
    _normalize_header_value,
    apply_dify_metadata_if_enabled,
    build_dify_headers,
)

_ENABLED = "enabled"
_APP_ID_HEADER = "X-Dify-App-Id"
_SOURCE_HEADER = "X-Dify-Source"
_SOURCE_VALUE = "dify"


# ---------------------------------------------------------------------------
# _normalize_header_value
# ---------------------------------------------------------------------------


def test_normalize_uuid_passthrough() -> None:
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert _normalize_header_value(uuid) == uuid


def test_normalize_preserves_punctuation() -> None:
    assert _normalize_header_value("a[b]c{d}e") == "a[b]c{d}e"


def test_normalize_strips_cr_lf() -> None:
    assert _normalize_header_value("a\r\nb") == "ab"


def test_normalize_strips_other_control_chars() -> None:
    assert _normalize_header_value("a\x00b\x07c") == "abc"


def test_normalize_coerces_non_string() -> None:
    assert _normalize_header_value(12345) == "12345"


def test_normalize_returns_empty_for_none() -> None:
    assert _normalize_header_value(None) == ""


def test_normalize_truncates_to_256_chars() -> None:
    s = "a" * 1024
    assert len(_normalize_header_value(s)) == 256


def test_normalize_returns_empty_for_all_control_chars() -> None:
    assert _normalize_header_value("\r\n\t\x00") == ""


# ---------------------------------------------------------------------------
# build_dify_headers
# ---------------------------------------------------------------------------


def test_build_headers_with_valid_app_id() -> None:
    headers = build_dify_headers("app-123")
    assert headers == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_build_headers_with_empty_app_id() -> None:
    assert build_dify_headers("") == {}


def test_build_headers_with_none_app_id() -> None:
    assert build_dify_headers(None) == {}


def test_build_headers_strips_cr_lf_in_app_id() -> None:
    headers = build_dify_headers("app\r\n123")
    assert headers == {
        _APP_ID_HEADER: "app123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# apply_dify_metadata_if_enabled — disabled / no-op paths
# ---------------------------------------------------------------------------


def test_disabled_does_not_set_extra_headers() -> None:
    credentials = {"app_id": "app-123"}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_disabled_with_other_value_does_not_set_extra_headers() -> None:
    credentials = {"app_id": "app-123", "enable_request_metadata": "disabled"}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_disabled_with_random_value_does_not_set_extra_headers() -> None:
    credentials = {"app_id": "app-123", "enable_request_metadata": "yes-please"}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_without_app_id_does_not_set_extra_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_with_empty_app_id_does_not_set_extra_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": ""}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_with_none_app_id_does_not_set_extra_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": None}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" not in credentials


# ---------------------------------------------------------------------------
# apply_dify_metadata_if_enabled — enabled / positive paths
# ---------------------------------------------------------------------------


def test_enabled_with_app_id_attaches_both_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    apply_dify_metadata_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_enabled_stringifies_non_string_app_id() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": 12345}
    apply_dify_metadata_if_enabled(credentials)
    assert credentials["extra_headers"][_APP_ID_HEADER] == "12345"
    assert credentials["extra_headers"][_SOURCE_HEADER] == _SOURCE_VALUE


def test_enabled_preserves_existing_extra_headers() -> None:
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": {"X-Custom-Header": "value"},
    }
    apply_dify_metadata_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        "X-Custom-Header": "value",
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_enabled_dify_keys_override_caller_on_collision() -> None:
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": {
            _APP_ID_HEADER: "old-value",
            _SOURCE_HEADER: "old-source",
            "X-Custom-Header": "value",
        },
    }
    apply_dify_metadata_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
        "X-Custom-Header": "value",
    }


def test_enabled_does_not_mutate_caller_dict_reference() -> None:
    existing = {"X-Custom-Header": "value"}
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": existing,
    }
    apply_dify_metadata_if_enabled(credentials)
    assert existing == {"X-Custom-Header": "value"}
    assert credentials["extra_headers"] is not existing
    assert credentials["extra_headers"] == {
        "X-Custom-Header": "value",
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_garbage_credentials() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    apply_dify_metadata_if_enabled(credentials)
    assert "extra_headers" in credentials


def test_helper_handles_extra_headers_as_none() -> None:
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": None,
    }
    apply_dify_metadata_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------


def test_helper_is_imported_and_used_in_llm() -> None:
    """The helper is wired into ``_setup_hunyuan_client`` in ``models/llm/llm.py``.

    Note: Hunyuan uses the official ``tencentcloud-sdk-python`` SDK.
    The SDK's ``ChatCompletionsRequest`` carries a ``headers`` attribute
    which ``HunyuanClient.ChatCompletions`` forwards via
    ``_call_and_deserialize(..., headers=request.headers)``. The Dify
    headers reach the Tencent Hunyuan endpoint by assigning
    ``credentials.get("extra_headers", {})`` onto ``request.headers``
    right before each ``client.ChatCompletions(request)`` call.

    The helper itself runs in ``_setup_hunyuan_client``, which is the
    shared setup helper used by both ``_invoke`` and
    ``validate_credentials``, so the helper runs at both call sites
    without any further wiring.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    llm_source = llm_path.read_text(encoding="utf-8")
    assert "from ._metadata import apply_dify_metadata_if_enabled" in llm_source
    assert "apply_dify_metadata_if_enabled(credentials)" in llm_source
    # Both call sites attach `xxx.headers = extra_headers` before the
    # `client.ChatCompletions(xxx)` invocation. The first site uses
    # `request`, the second uses `req`. The guard below confirms both
    # wiring points are present.
    assert (
        llm_source.count("request.headers = extra_headers")
        + llm_source.count("req.headers = extra_headers")
    ) == 2
    assert llm_source.count("client.ChatCompletions(request)") >= 1
    assert llm_source.count("client.ChatCompletions(req)") >= 1


def test_helper_module_is_reachable_from_llm() -> None:
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "apply_dify_metadata_if_enabled")
    assert callable(helper_module.apply_dify_metadata_if_enabled)
    assert hasattr(helper_module, "build_dify_headers")
    assert callable(helper_module.build_dify_headers)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-vv"]))
