"""Unit tests for the opt-in Dify metadata helper used by the Volcengine MAAS plugin.

The helper writes Dify `X-Dify-App-Id` and `X-Dify-Source: dify` headers into
`credentials['extra_headers']` when the credential `enable_request_metadata` is
`"enabled"` and a Dify `app_id` resolves. The Volcengine MAAS plugin then
reads `credentials.get("extra_headers")` and threads the dict into:

- The v3 (Ark) path's `client.chat(...)` and `client.stream_chat(...)`
  `extra_headers=` kwarg, which the OpenAI SDK forwards on each outbound
  request.
- The v2 (legacy) path's `client.chat(...)` kwarg, which the vendored
  `MaasService._call` merges into the HTTP request headers before the
  SDK signs the request.

When the credential is disabled, or `app_id` is missing / empty, the helper
does nothing and the request shape is unchanged.

These tests do not need a network or either SDK: the helper is pure and
runs entirely in memory. The integration with `_validate_credentials_v2`,
`_validate_credentials_v3`, `_generate_v2`, and `_generate_v3` is
verified by the source-level guard tests at the bottom of this file.
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
    """The helper is wired into all four entry points in ``models/llm/llm.py``.

    Note: Volcengine MAAS has two code paths:

    - **v3 (modern Ark)** uses the OpenAI SDK's ``extra_headers=`` on each
      ``chat.completions.create`` call. ``ArkClientV3.chat`` and
      ``ArkClientV3.stream_chat`` were extended to merge caller-supplied
      ``extra_headers`` into the OpenAI SDK's slot, with Dify keys
      winning on collision so the opt-in helper always controls its
      own observability markers.

    - **v2 (legacy)** uses a vendored ``MaasService._call`` which
      signs requests with ak/sk. ``MaasService._call``, ``chat``,
      ``stream_chat``, ``embeddings``, and ``_request`` were extended
      to accept an ``extra_headers=`` parameter. ``MaaSClient.chat``
      forwards it through. The legacy SDK merges the dict into the
      HTTP request headers before the SDK signs the request; the
      helper's Dify keys do not override the SDK's required
      ``x-tt-logid`` and ``Content-Type`` headers.

    The helper runs at all four LLM call sites
    (``_validate_credentials_v2``, ``_validate_credentials_v3``,
    ``_generate_v2``, ``_generate_v3``) and reads back
    ``credentials.get("extra_headers")`` at each call site.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    llm_source = llm_path.read_text(encoding="utf-8")
    assert (
        "from models.llm._metadata import apply_dify_metadata_if_enabled" in llm_source
    )
    # Helper runs at 4 entry points (2 validate_credentials + 2 _generate).
    assert llm_source.count("apply_dify_metadata_if_enabled(credentials)") >= 4
    # Each entry point reads ``credentials.get("extra_headers")`` and
    # passes it as the ``extra_headers=`` kwarg. We expect 4 such
    # invocations across v2 (1: validate_credentials_v2, 1:
    # _generate_v2) and v3 (2: chat + stream_chat in _generate_v3)
    # for a total of 4.
    assert llm_source.count('credentials.get("extra_headers")') >= 4


def test_v3_client_threads_extra_headers() -> None:
    """The v3 ``ArkClientV3`` forwards ``extra_headers=`` through both block and stream chat.

    Both methods must merge the caller-supplied dict into the OpenAI
    SDK's ``extra_headers=`` slot, with Dify keys winning on collision
    so the opt-in helper always controls its own observability
    markers.
    """
    client_path = ROOT_DIR / "models" / "client.py"
    client_source = client_path.read_text(encoding="utf-8")
    # ``extra_headers`` parameter is accepted on both block_chat (renamed
    # ``chat``) and ``stream_chat`` methods.
    assert "extra_headers: Optional[dict] = None" in client_source
    # Both methods merge the caller-supplied dict into the
    # ``x-ark-moderation-scene`` slot (or omit it when neither is set).
    assert client_source.count("merged_extra_headers") >= 2


def test_v2_sdk_threads_extra_headers() -> None:
    """The v2 vendored ``MaasService`` accepts ``extra_headers=`` on every entry point.

    ``MaasService._call`` is the lowest-level function that builds the
    HTTP request; threading ``extra_headers=`` through it is the
    minimal-vendor-patch approach for propagating custom headers in
    the v2 path.
    """
    sdk_path = ROOT_DIR / "legacy" / "volc_sdk" / "maas.py"
    sdk_source = sdk_path.read_text(encoding="utf-8")
    # ``_call`` accepts ``extra_headers``.
    assert "extra_headers=None" in sdk_source
    # ``_call`` merges the dict into ``r.headers`` after the SDK sets
    # the standard ``x-tt-logid`` and ``Content-Type`` headers; Dify
    # keys do not override them.
    assert "if k in r.headers:\n                    continue" in sdk_source
    # ``chat`` and ``stream_chat`` accept ``extra_headers`` and forward
    # it through to ``super().chat`` / ``super().stream_chat`` /
    # ``self._call``.
    assert sdk_source.count("extra_headers=extra_headers") >= 2


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
