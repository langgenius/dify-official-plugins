"""Unit tests for Claude 5 (Sonnet 5 / Fable 5) helpers in model_ids.py.

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

SONNET5 = "anthropic.claude-sonnet-5"
FABLE5 = "anthropic.claude-fable-5"


class TestRegistry:
    def test_family_registered(self):
        family = model_ids.BEDROCK_MODEL_IDS["anthropic claude 5"]
        assert family["Sonnet 5"] == SONNET5
        assert family["Fable 5"] == FABLE5

    def test_get_model_id(self):
        assert model_ids.get_model_id("anthropic claude 5", "Sonnet 5") == SONNET5
        assert model_ids.get_model_id("anthropic claude 5", "Fable 5") == FABLE5


class TestIsClaude5:
    def test_bare_ids(self):
        assert model_ids.is_claude5_model(SONNET5)
        assert model_ids.is_claude5_model(FABLE5)

    def test_other_models_are_not_claude5(self):
        assert not model_ids.is_claude5_model("anthropic.claude-opus-4-8")
        assert not model_ids.is_claude5_model("anthropic.claude-sonnet-4-6")

    def test_profile_ids(self):
        assert model_ids.is_claude5_profile_id(f"global.{SONNET5}")
        assert model_ids.is_claude5_profile_id(f"us.{FABLE5}")
        assert model_ids.is_claude5_profile_id(SONNET5)
        assert not model_ids.is_claude5_profile_id("global.anthropic.claude-opus-4-8")


class TestResolveProfileId:
    @pytest.mark.parametrize("region", [
        "us-east-1", "eu-central-1", "ap-northeast-1", "sa-east-1",
    ])
    def test_global_works_from_any_region(self, region):
        # global must bypass the legacy 5-region whitelist entirely
        assert (
            model_ids.resolve_claude5_profile_id(SONNET5, "global", region)
            == f"global.{SONNET5}"
        )

    @pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
    def test_geographic_us_regions(self, region):
        assert (
            model_ids.resolve_claude5_profile_id(FABLE5, "geographic", region)
            == f"us.{FABLE5}"
        )

    @pytest.mark.parametrize("region", ["ca-central-1", "ca-west-1"])
    def test_geographic_canada_maps_to_us_profile(self, region):
        # Per the model card, the US geo profile serves CA source regions
        assert (
            model_ids.resolve_claude5_profile_id(SONNET5, "geographic", region)
            == f"us.{SONNET5}"
        )

    @pytest.mark.parametrize("region", ["eu-central-1", "eu-west-1", "ap-northeast-1"])
    def test_geographic_unsupported_regions_raise(self, region):
        with pytest.raises(ValueError, match="Global"):
            model_ids.resolve_claude5_profile_id(SONNET5, "geographic", region)

    def test_disabled_raises(self):
        with pytest.raises(ValueError, match="inference profile"):
            model_ids.resolve_claude5_profile_id(SONNET5, "disabled", "us-east-1")

    def test_unknown_cross_region_value_raises(self):
        with pytest.raises(ValueError):
            model_ids.resolve_claude5_profile_id(SONNET5, "", "us-east-1")

    @pytest.mark.parametrize("cross_region", ["global", "geographic"])
    def test_govcloud_rejected(self, cross_region):
        # GovCloud is a separate partition — commercial profile IDs are invalid
        with pytest.raises(ValueError, match="GovCloud"):
            model_ids.resolve_claude5_profile_id(SONNET5, cross_region, "us-gov-west-1")


class TestFallbackId:
    def test_global_prefix_preserved(self):
        assert (
            model_ids.get_claude5_fallback_model_id(f"global.{FABLE5}")
            == "global.anthropic.claude-opus-4-8"
        )

    def test_us_prefix_preserved(self):
        assert (
            model_ids.get_claude5_fallback_model_id(f"us.{SONNET5}")
            == "us.anthropic.claude-opus-4-8"
        )
