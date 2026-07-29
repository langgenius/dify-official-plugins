"""Unit tests for cache_config: Claude 5 registration and global. prefix handling."""
import importlib.util
from pathlib import Path

_CACHE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "models" / "llm" / "cache_config.py"
)
_spec = importlib.util.spec_from_file_location("cache_config", _CACHE_CONFIG_PATH)
cache_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cache_config)


class TestClaude5CacheRegistration:
    def test_sonnet5_supported_with_min_4096(self):
        assert cache_config.is_cache_supported("anthropic.claude-sonnet-5")
        cfg = cache_config.get_cache_config("anthropic.claude-sonnet-5")
        assert cfg["min_tokens"] == 4096
        assert cfg["supported_fields"] == ["system", "messages", "tools"]

    def test_fable5_supported_with_min_1024(self):
        assert cache_config.is_cache_supported("anthropic.claude-fable-5")
        cfg = cache_config.get_cache_config("anthropic.claude-fable-5")
        assert cfg["min_tokens"] == 1024
        assert cfg["supported_fields"] == ["system", "messages", "tools"]


class TestGlobalPrefixStripping:
    def test_global_prefixed_claude5(self):
        assert cache_config.is_cache_supported("global.anthropic.claude-sonnet-5")
        cfg = cache_config.get_cache_config("global.anthropic.claude-fable-5")
        assert cfg["min_tokens"] == 1024

    def test_global_prefixed_existing_model(self):
        # Regression: global. profiles previously fell through to defaults
        assert cache_config.is_cache_supported("global.anthropic.claude-opus-4-8")
        cfg = cache_config.get_cache_config("global.anthropic.claude-opus-4-8")
        assert cfg["min_tokens"] == 4096

    def test_us_prefix_still_works(self):
        assert cache_config.is_cache_supported("us.anthropic.claude-sonnet-5")

    def test_jp_au_prefixes_stripped(self):
        # jp./au. profiles exist for Opus 4.7/4.8-era models
        assert cache_config.is_cache_supported("jp.anthropic.claude-opus-4-8")
        assert cache_config.is_cache_supported("au.anthropic.claude-opus-4-8")
