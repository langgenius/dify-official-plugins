"""Unit tests for the 4.5-generation Claude (Sonnet/Haiku 4.5, Sonnet/Opus 4.6,
Opus 4.7/4.8) helpers in model_ids.py.

model_ids.py has no third-party imports, so we load it directly by path:
no dify_plugin or boto3 required.
"""
import importlib.util
from pathlib import Path

import pytest

_MODEL_IDS_PATH = (
    Path(__file__).resolve().parent.parent / "models" / "llm" / "model_ids.py"
)
_spec = importlib.util.spec_from_file_location("model_ids", _MODEL_IDS_PATH)
model_ids = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model_ids)

SONNET46 = "anthropic.claude-sonnet-4-6"
OPUS46 = "anthropic.claude-opus-4-6-v1"
TOKYO = "ap-northeast-1"


class TestIsClaude45:
    def test_bare_ids(self):
        for model_id in model_ids.CLAUDE45_PROFILE_PREFIXES:
            assert model_ids.is_claude45_model(model_id)

    def test_other_models_are_not_claude45(self):
        assert not model_ids.is_claude45_model("anthropic.claude-sonnet-4-20250514-v1:0")
        assert not model_ids.is_claude45_model("anthropic.claude-sonnet-5")
        assert not model_ids.is_claude45_model("anthropic.claude-3-haiku-20240307-v1:0")


class TestResolveProfileId:
    def test_global_works_from_apac_region(self):
        # This is the issue's #1 dead end: 'disabled' always fails for these
        # models, and 'global' is the documented way out.
        assert (
            model_ids.resolve_claude45_profile_id(SONNET46, "global", TOKYO)
            == f"global.{SONNET46}"
        )

    @pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
    def test_geographic_us_regions(self, region):
        assert (
            model_ids.resolve_claude45_profile_id(SONNET46, "geographic", region)
            == f"us.{SONNET46}"
        )

    @pytest.mark.parametrize("region", ["eu-central-1", "eu-west-1"])
    def test_geographic_eu_regions(self, region):
        assert (
            model_ids.resolve_claude45_profile_id(SONNET46, "geographic", region)
            == f"eu.{SONNET46}"
        )

    def test_geographic_apac_region_raises_and_mentions_japan(self):
        # Issue's #2 dead end: ap-northeast-1 resolves to 'apac', and no
        # apac. profile exists for this generation. SONNET46 has a jp.
        # profile, so the error should point at it.
        with pytest.raises(ValueError, match="japan"):
            model_ids.resolve_claude45_profile_id(SONNET46, "geographic", TOKYO)

    def test_geographic_apac_region_without_jp_profile_omits_japan(self):
        # OPUS46 has no jp. profile (not in JP_PROFILE_MODELS): the error
        # must not suggest an option that will also fail.
        assert OPUS46 not in model_ids.JP_PROFILE_MODELS
        with pytest.raises(ValueError) as excinfo:
            model_ids.resolve_claude45_profile_id(OPUS46, "geographic", TOKYO)
        assert "japan" not in str(excinfo.value)

    def test_disabled_raises(self):
        with pytest.raises(ValueError, match="inference profile"):
            model_ids.resolve_claude45_profile_id(SONNET46, "disabled", TOKYO)

    def test_disabled_from_us_region_also_raises(self):
        # The bug is generation-wide, not region-specific: on-demand is not
        # offered anywhere for these models, regardless of the caller's region.
        with pytest.raises(ValueError, match="inference profile"):
            model_ids.resolve_claude45_profile_id(SONNET46, "disabled", "us-east-1")


class TestExistingBehaviorUnchanged:
    """Sibling generations must resolve exactly as before this fix."""

    def test_claude5_untouched(self):
        assert (
            model_ids.resolve_claude5_profile_id("anthropic.claude-sonnet-5", "global", TOKYO)
            == "global.anthropic.claude-sonnet-5"
        )

    def test_claude4_0_not_claude45(self):
        # Sonnet 4 (2025-05) supports on-demand and an apac. profile; it must
        # not be swept into the 4.5-generation profile-only handling.
        assert not model_ids.is_claude45_model("anthropic.claude-sonnet-4-20250514-v1:0")

    def test_japan_cross_region_unaffected(self):
        # 'japan' is resolved by resolve_japan_profile_id before is_claude45_model
        # is ever consulted in the dispatch (see llm.py); this test pins the
        # data these two helpers agree on so a future edit cannot desync them.
        assert SONNET46 in model_ids.CLAUDE45_PROFILE_PREFIXES
        assert SONNET46 in model_ids.JP_PROFILE_MODELS
        assert (
            model_ids.resolve_japan_profile_id(SONNET46, TOKYO) == f"jp.{SONNET46}"
        )
