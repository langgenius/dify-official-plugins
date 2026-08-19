"""Unit tests for the Japan ('jp.') geographic inference profile helpers.

model_ids.py has no third-party imports, so we load it directly by path —
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
SONNET4 = "anthropic.claude-sonnet-4-20250514-v1:0"
TOKYO = "ap-northeast-1"
OSAKA = "ap-northeast-3"


class TestJpProfileModels:
    def test_registry_contents(self):
        # Live-verified via list-inference-profiles in ap-northeast-1.
        assert SONNET46 in model_ids.JP_PROFILE_MODELS
        assert "anthropic.claude-haiku-4-5-20251001-v1:0" in model_ids.JP_PROFILE_MODELS
        assert "anthropic.claude-opus-4-8" in model_ids.JP_PROFILE_MODELS

    def test_models_without_jp_profiles_absent(self):
        for model_id in (
            SONNET4,
            "anthropic.claude-opus-4-6-v1",
            "anthropic.claude-sonnet-5",
            "anthropic.claude-3-haiku-20240307-v1:0",
        ):
            assert model_id not in model_ids.JP_PROFILE_MODELS


class TestResolveJapanProfileId:
    def test_tokyo(self):
        assert model_ids.resolve_japan_profile_id(SONNET46, TOKYO) == f"jp.{SONNET46}"

    def test_osaka(self):
        assert model_ids.resolve_japan_profile_id(SONNET46, OSAKA) == f"jp.{SONNET46}"

    def test_outside_japan_raises(self):
        with pytest.raises(ValueError, match="only available from"):
            model_ids.resolve_japan_profile_id(SONNET46, "us-east-1")

    def test_model_without_jp_profile_raises(self):
        # Sonnet 4 (2025-05) has an apac. profile but no jp. profile.
        with pytest.raises(ValueError, match="no 'jp.' geographic inference profile"):
            model_ids.resolve_japan_profile_id(SONNET4, TOKYO)

    def test_never_falls_back_outside_japan(self):
        """A silent apac. fallback would break the data-residency guarantee."""
        for region in ("us-east-1", "eu-west-1", "ap-southeast-1", "ap-southeast-2"):
            with pytest.raises(ValueError):
                model_ids.resolve_japan_profile_id(SONNET46, region)

    def test_result_is_strippable(self):
        resolved = model_ids.resolve_japan_profile_id(SONNET46, TOKYO)
        assert model_ids.strip_profile_prefix(resolved) == SONNET46


class TestExistingResolutionUnchanged:
    """Adding the jp. option must not alter geographic/global resolution."""

    def test_tokyo_geographic_is_still_apac(self):
        assert model_ids.get_region_area(TOKYO) == "apac"

    def test_tokyo_global(self):
        assert model_ids.get_region_area(TOKYO, prefer_global=True) == "global"

    def test_us_and_eu_unchanged(self):
        assert model_ids.get_region_area("us-east-1") == "us"
        assert model_ids.get_region_area("eu-west-1") == "eu"

    def test_unknown_region_unchanged(self):
        assert model_ids.get_region_area("sa-east-1") is None
