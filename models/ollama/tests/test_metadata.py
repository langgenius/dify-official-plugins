"""Unit tests for the opt-in Dify metadata helper used by the Ollama plugin.

The helper writes Dify `X-Dify-App-Id` and `X-Dify-Source: dify` headers into
`credentials['extra_headers']` when the credential `enable_request_metadata` is
`"enabled"` and a Dify `app_id` resolves. The Ollama plugin's `_generate` method
merges `credentials['extra_headers']` into the outbound `requests.post` headers,
so writing to that credential is the carrier for observability metadata.

When the credential is disabled, or `app_id` is missing / empty, the helper
does nothing and the request shape is unchanged.

These tests use `unittest.TestCase` + `unittest.mock` to match the existing
test style in `tests/test_llm.py`. The helper is pure and runs entirely in
memory; the integration with `_generate` is verified by the source-level
guard tests at the bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm._metadata import (
    _normalize_header_value,
    apply_dify_headers_if_enabled,
    build_dify_headers,
)

_ENABLED = "enabled"
_APP_ID_HEADER = "X-Dify-App-Id"
_SOURCE_HEADER = "X-Dify-Source"
_SOURCE_VALUE = "dify"


# ---------------------------------------------------------------------------
# _normalize_header_value
# ---------------------------------------------------------------------------


class NormalizeHeaderValueTest(TestCase):
    def test_uuid_passthrough(self) -> None:
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(_normalize_header_value(uuid), uuid)

    def test_preserves_punctuation(self) -> None:
        self.assertEqual(_normalize_header_value("a[b]c{d}e"), "a[b]c{d}e")

    def test_strips_cr_lf(self) -> None:
        self.assertEqual(_normalize_header_value("a\r\nb"), "ab")

    def test_strips_other_control_chars(self) -> None:
        self.assertEqual(_normalize_header_value("a\x00b\x07c"), "abc")

    def test_coerces_non_string(self) -> None:
        self.assertEqual(_normalize_header_value(12345), "12345")

    def test_returns_empty_for_none(self) -> None:
        self.assertEqual(_normalize_header_value(None), "")

    def test_truncates_to_256_chars(self) -> None:
        s = "a" * 1024
        self.assertEqual(len(_normalize_header_value(s)), 256)

    def test_returns_empty_for_all_control_chars(self) -> None:
        self.assertEqual(_normalize_header_value("\r\n\t\x00"), "")


# ---------------------------------------------------------------------------
# build_dify_headers
# ---------------------------------------------------------------------------


class BuildDifyHeadersTest(TestCase):
    def test_valid_app_id(self) -> None:
        self.assertEqual(
            build_dify_headers("app-123"),
            {_APP_ID_HEADER: "app-123", _SOURCE_HEADER: _SOURCE_VALUE},
        )

    def test_empty_app_id(self) -> None:
        self.assertEqual(build_dify_headers(""), {})

    def test_none_app_id(self) -> None:
        self.assertEqual(build_dify_headers(None), {})

    def test_strips_cr_lf_in_app_id(self) -> None:
        self.assertEqual(
            build_dify_headers("app\r\n123"),
            {_APP_ID_HEADER: "app123", _SOURCE_HEADER: _SOURCE_VALUE},
        )


# ---------------------------------------------------------------------------
# apply_dify_headers_if_enabled — disabled / no-op paths
# ---------------------------------------------------------------------------


class ApplyDifyHeadersDisabledTest(TestCase):
    def test_unset_does_not_set_extra_headers(self) -> None:
        credentials = {"app_id": "app-123"}
        apply_dify_headers_if_enabled(credentials)
        self.assertNotIn("extra_headers", credentials)

    def test_disabled_value_does_not_set_extra_headers(self) -> None:
        credentials = {"app_id": "app-123", "enable_request_metadata": "disabled"}
        apply_dify_headers_if_enabled(credentials)
        self.assertNotIn("extra_headers", credentials)

    def test_random_value_does_not_set_extra_headers(self) -> None:
        credentials = {"app_id": "app-123", "enable_request_metadata": "yes-please"}
        apply_dify_headers_if_enabled(credentials)
        self.assertNotIn("extra_headers", credentials)

    def test_enabled_without_app_id_does_not_set_extra_headers(self) -> None:
        credentials = {"enable_request_metadata": _ENABLED}
        apply_dify_headers_if_enabled(credentials)
        self.assertNotIn("extra_headers", credentials)

    def test_enabled_with_empty_app_id_does_not_set_extra_headers(self) -> None:
        credentials = {"enable_request_metadata": _ENABLED, "app_id": ""}
        apply_dify_headers_if_enabled(credentials)
        self.assertNotIn("extra_headers", credentials)

    def test_enabled_with_none_app_id_does_not_set_extra_headers(self) -> None:
        credentials = {"enable_request_metadata": _ENABLED, "app_id": None}
        apply_dify_headers_if_enabled(credentials)
        self.assertNotIn("extra_headers", credentials)


# ---------------------------------------------------------------------------
# apply_dify_headers_if_enabled — enabled / positive paths
# ---------------------------------------------------------------------------


class ApplyDifyHeadersEnabledTest(TestCase):
    def test_attaches_both_headers(self) -> None:
        credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
        apply_dify_headers_if_enabled(credentials)
        self.assertEqual(
            credentials["extra_headers"],
            {_APP_ID_HEADER: "app-123", _SOURCE_HEADER: _SOURCE_VALUE},
        )

    def test_stringifies_non_string_app_id(self) -> None:
        credentials = {"enable_request_metadata": _ENABLED, "app_id": 12345}
        apply_dify_headers_if_enabled(credentials)
        self.assertEqual(credentials["extra_headers"][_APP_ID_HEADER], "12345")
        self.assertEqual(credentials["extra_headers"][_SOURCE_HEADER], _SOURCE_VALUE)

    def test_preserves_existing_extra_headers(self) -> None:
        credentials = {
            "enable_request_metadata": _ENABLED,
            "app_id": "app-123",
            "extra_headers": {"X-Custom-Header": "value"},
        }
        apply_dify_headers_if_enabled(credentials)
        self.assertEqual(
            credentials["extra_headers"],
            {
                "X-Custom-Header": "value",
                _APP_ID_HEADER: "app-123",
                _SOURCE_HEADER: _SOURCE_VALUE,
            },
        )

    def test_dify_keys_override_caller_on_collision(self) -> None:
        credentials = {
            "enable_request_metadata": _ENABLED,
            "app_id": "app-123",
            "extra_headers": {
                _APP_ID_HEADER: "old-value",
                _SOURCE_HEADER: "old-source",
                "X-Custom-Header": "value",
            },
        }
        apply_dify_headers_if_enabled(credentials)
        self.assertEqual(
            credentials["extra_headers"],
            {
                _APP_ID_HEADER: "app-123",
                _SOURCE_HEADER: _SOURCE_VALUE,
                "X-Custom-Header": "value",
            },
        )

    def test_does_not_mutate_caller_dict_reference(self) -> None:
        existing = {"X-Custom-Header": "value"}
        credentials = {
            "enable_request_metadata": _ENABLED,
            "app_id": "app-123",
            "extra_headers": existing,
        }
        apply_dify_headers_if_enabled(credentials)
        # The caller's existing dict reference is unchanged.
        self.assertEqual(existing, {"X-Custom-Header": "value"})
        # But the credentials dict now points to a new merged dict.
        self.assertIsNot(credentials["extra_headers"], existing)
        self.assertEqual(
            credentials["extra_headers"],
            {
                "X-Custom-Header": "value",
                _APP_ID_HEADER: "app-123",
                _SOURCE_HEADER: _SOURCE_VALUE,
            },
        )


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


class ApplyDifyHeadersRobustnessTest(TestCase):
    def test_never_raises_on_garbage_credentials(self) -> None:
        credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
        apply_dify_headers_if_enabled(credentials)
        self.assertIn("extra_headers", credentials)

    def test_handles_extra_headers_as_non_dict(self) -> None:
        credentials = {
            "enable_request_metadata": _ENABLED,
            "app_id": "app-123",
            "extra_headers": None,
        }
        apply_dify_headers_if_enabled(credentials)
        self.assertEqual(
            credentials["extra_headers"],
            {_APP_ID_HEADER: "app-123", _SOURCE_HEADER: _SOURCE_VALUE},
        )


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------


class SourceLevelGuardTest(TestCase):
    def test_helper_is_used_in_llm_py(self) -> None:
        """The helper is wired into `_generate` and merges into the headers."""
        llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
        source = llm_path.read_text(encoding="utf-8")
        # The helper is imported.
        self.assertIn(
            "from models.llm._metadata import apply_dify_headers_if_enabled", source
        )
        # And called exactly once (in `_generate`).
        self.assertEqual(source.count("apply_dify_headers_if_enabled(credentials)"), 1)
        # The merge step exists in `_generate` after the helper call.
        generate_idx = source.index("def _generate(")
        generate_block = source[generate_idx:]
        idx_helper = generate_block.index("apply_dify_headers_if_enabled(credentials)")
        idx_merge = generate_block.index("headers.update(extra_headers)")
        idx_post = generate_block.index("requests.post(")
        self.assertLess(idx_helper, idx_merge)
        self.assertLess(idx_merge, idx_post)

    def test_helper_module_is_reachable_from_llm(self) -> None:
        helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
        self.assertTrue(helper_path.is_file(), f"missing helper: {helper_path}")
        import models.llm._metadata as helper_module

        self.assertTrue(hasattr(helper_module, "apply_dify_headers_if_enabled"))
        self.assertTrue(callable(helper_module.apply_dify_headers_if_enabled))
        self.assertTrue(hasattr(helper_module, "build_dify_headers"))
        self.assertTrue(callable(helper_module.build_dify_headers))


if __name__ == "__main__":
    import unittest

    unittest.main()
