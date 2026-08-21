"""Unit tests for the Claude 4.5+ profile-prefix helpers in
``models.llm.model_ids``.

Pins the behavior of:

- ``CLAUDE45_PROFILE_PREFIXES`` membership (7 model IDs)
- ``is_claude45_model`` (bare-ID exact match)
- ``is_claude45_profile_id`` (bare or profile-prefixed)
- ``resolve_claude45_profile_id`` (global, geographic, disabled, GovCloud)

Background: Claude 4.5-generation models (Sonnet 4.5+, Haiku 4.5+, Opus
4.5–4.8) are INFERENCE_PROFILE-only on Bedrock — bare-ID on-demand
converse returns ValidationException. They are not invocable through
the existing Claude 5 path (which only covers the claude-opus-5 /
claude-sonnet-5 / claude-fable-5 family), so a parallel set of helpers
is needed.

Issue: #3664.
"""

from __future__ import annotations

import importlib
import pytest

model_ids_mod = importlib.import_module("models.llm.model_ids")

CLAUDE45_IDS = [
    "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic.claude-opus-4-5-20251101-v1:0",
    "anthropic.claude-sonnet-4-6",
    "anthropic.claude-opus-4-6-v1",
    "anthropic.claude-opus-4-7",
    "anthropic.claude-opus-4-8",
]


class TestClaude45PrefixesMembership:
    """The 7 live-verified Claude 4.5+ model IDs must all be in
    ``CLAUDE45_PROFILE_PREFIXES`` with the correct supported prefixes.
    """

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_model_id_is_in_claude45_set(self, model_id: str) -> None:
        assert model_id in model_ids_mod.CLAUDE45_PROFILE_PREFIXES

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_each_claude45_model_supports_global(self, model_id: str) -> None:
        assert "global" in model_ids_mod.CLAUDE45_PROFILE_PREFIXES[model_id]

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_each_claude45_model_supports_us(self, model_id: str) -> None:
        assert "us" in model_ids_mod.CLAUDE45_PROFILE_PREFIXES[model_id]

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_each_claude45_model_supports_eu(self, model_id: str) -> None:
        assert "eu" in model_ids_mod.CLAUDE45_PROFILE_PREFIXES[model_id]

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_each_claude45_model_supports_jp(self, model_id: str) -> None:
        """Issue #3664 lists all 4.5+ Anthropic models in ap-northeast-1
        with jp. profiles. Per the issue body:
        ``jp.anthropic.claude-sonnet-4-6``, ``jp.anthropic.claude-haiku-4-5``,
        ``jp.anthropic.claude-opus-4-7``, ``jp.anthropic.claude-opus-4-8``,
        etc.
        """
        assert "jp" in model_ids_mod.CLAUDE45_PROFILE_PREFIXES[model_id]

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_no_claude45_model_supports_apac(self, model_id: str) -> None:
        """``apac.anthropic.*`` profiles stop at Sonnet 4. There is no
        apac. profile for any 4.5-generation Anthropic model.
        """
        assert "apac" not in model_ids_mod.CLAUDE45_PROFILE_PREFIXES[model_id]


class TestIsClaude45Model:
    """``is_claude45_model`` returns True for exact bare-ID match only."""

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_bare_id_is_recognized(self, model_id: str) -> None:
        assert model_ids_mod.is_claude45_model(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "anthropic.claude-3-haiku-20240307-v1:0",  # 3.x, on-demand supported
            "anthropic.claude-sonnet-4-20250514-v1:0",  # 4.0, on-demand supported
            "anthropic.claude-opus-5",  # 5, handled by CLAUDE5 path
            "anthropic.claude-fable-5",
            "anthropic.claude-sonnet-5",
            "cohere.command-r-plus",  # different family
            "amazon.nova-pro",
            "",  # empty
        ],
    )
    def test_non_claude45_id_is_rejected(self, model_id: str) -> None:
        assert model_ids_mod.is_claude45_model(model_id) is False


class TestIsClaude45ProfileId:
    """``is_claude45_profile_id`` accepts both bare and profile-prefixed
    forms.
    """

    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_bare_id_is_recognized(self, model_id: str) -> None:
        assert model_ids_mod.is_claude45_profile_id(model_id) is True

    @pytest.mark.parametrize("prefix", ["global.", "us.", "eu.", "jp."])
    @pytest.mark.parametrize("model_id", CLAUDE45_IDS)
    def test_prefixed_id_is_recognized(self, prefix: str, model_id: str) -> None:
        assert model_ids_mod.is_claude45_profile_id(f"{prefix}{model_id}") is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "anthropic.claude-3-haiku-20240307-v1:0",
            "anthropic.claude-sonnet-4-20250514-v1:0",
            "anthropic.claude-opus-5",
            "cohere.command-r-plus",
            "",
        ],
    )
    def test_non_claude45_id_is_rejected(self, model_id: str) -> None:
        assert model_ids_mod.is_claude45_profile_id(model_id) is False


class TestResolveClaude45ProfileId:
    """``resolve_claude45_profile_id`` resolves the bare model ID to a
    profile-prefixed ID, raising ValueError for combinations that
    cannot be served.
    """

    MODEL_ID = "anthropic.claude-sonnet-4-6"

    def test_global_resolves_to_global_prefix(self) -> None:
        assert (
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "global", "us-east-1")
            == "global.anthropic.claude-sonnet-4-6"
        )

    def test_global_works_from_japan(self) -> None:
        """Global profiles are available from virtually all commercial
        regions, including ap-northeast-1.
        """
        assert (
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "global", "ap-northeast-1")
            == "global.anthropic.claude-sonnet-4-6"
        )

    def test_geographic_us_resolves_to_us_prefix(self) -> None:
        assert (
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "geographic", "us-east-1")
            == "us.anthropic.claude-sonnet-4-6"
        )

    def test_geographic_eu_resolves_to_eu_prefix(self) -> None:
        assert (
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "geographic", "eu-west-1")
            == "eu.anthropic.claude-sonnet-4-6"
        )

    def test_geographic_japan_ap_northeast_1_resolves_to_jp_prefix(self) -> None:
        """The Japan geographic profile is reachable from ap-northeast-1
        and ap-northeast-3 only. Issue #3664 verified this is the
        profile needed for data-residency in Japan.
        """
        assert (
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "geographic", "ap-northeast-1")
            == "jp.anthropic.claude-sonnet-4-6"
        )

    def test_geographic_japan_ap_northeast_3_resolves_to_jp_prefix(self) -> None:
        assert (
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "geographic", "ap-northeast-3")
            == "jp.anthropic.claude-sonnet-4-6"
        )

    def test_geographic_ap_singapore_does_not_resolve_to_apac(self) -> None:
        """4.5+ models have no apac. profile. From ap-southeast-1 (Singapore)
        the area resolves to 'apac' which is not in the allowed set —
        fall back to a user-actionable error.
        """
        with pytest.raises(ValueError, match=r"has no 'apac' geographic inference profile"):
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "geographic", "ap-southeast-1")

    def test_geographic_unknown_region_raises(self) -> None:
        """A region outside the standard area mapping (e.g. me-south-1,
        af-south-1) has no geo profile. User must use Global.
        """
        with pytest.raises(ValueError, match="only Global"):
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "geographic", "me-south-1")

    def test_disabled_raises_for_inference_profile_only_models(self) -> None:
        """Claude 4.5+ models are INFERENCE_PROFILE-only on Bedrock.
        Bare-ID on-demand invocation returns ValidationException. The
        helper must surface this as a clear ValueError, not silently
        return a bare ID.
        """
        with pytest.raises(ValueError, match="on-demand throughput"):
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "disabled", "us-east-1")

    def test_govcloud_raises(self) -> None:
        """Commercial inference profile IDs are not valid in AWS GovCloud."""
        with pytest.raises(ValueError, match="GovCloud"):
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "global", "us-gov-west-1")

    def test_invalid_cross_region_raises(self) -> None:
        """A typo in the cross_region parameter must surface as a
        user-actionable error.
        """
        with pytest.raises(ValueError, match="inference profile"):
            model_ids_mod.resolve_claude45_profile_id(self.MODEL_ID, "typo", "us-east-1")


class TestClaude45AndClaude5AreDisjoint:
    """The 4.5+ set and the Claude 5 set must be disjoint — no model
    appears in both. This guards against a future refactor that
    accidentally double-lists a model.
    """

    def test_no_overlap_between_sets(self) -> None:
        claude5_ids = set(model_ids_mod.CLAUDE5_PROFILE_PREFIXES.keys())
        claude45_ids = set(model_ids_mod.CLAUDE45_PROFILE_PREFIXES.keys())
        overlap = claude5_ids & claude45_ids
        assert overlap == set(), (
            f"Models appear in both CLAUDE5_PROFILE_PREFIXES and "
            f"CLAUDE45_PROFILE_PREFIXES: {overlap}"
        )

    def test_is_claude5_and_is_claude45_are_mutually_exclusive(self) -> None:
        claude5_ids = list(model_ids_mod.CLAUDE5_PROFILE_PREFIXES.keys())
        claude45_ids = list(model_ids_mod.CLAUDE45_PROFILE_PREFIXES.keys())
        for mid in claude5_ids:
            assert model_ids_mod.is_claude5_model(mid) is True
            assert model_ids_mod.is_claude45_model(mid) is False
        for mid in claude45_ids:
            assert model_ids_mod.is_claude5_model(mid) is False
            assert model_ids_mod.is_claude45_model(mid) is True
