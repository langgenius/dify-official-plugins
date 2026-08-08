"""Smoke-test provider registration against its declared tool manifests."""
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provider.llama import LlamaParseProvider


class LlamaParseProviderSmokeTest(unittest.TestCase):
    def test_provider_declares_manifest_tools(self) -> None:
        plugin_root = Path(__file__).resolve().parents[1]
        provider_manifest = yaml.safe_load(
            (plugin_root / "provider" / "llama.yaml").read_text()
        )
        provider = LlamaParseProvider()

        declared_tools = provider_manifest["tools"]
        self.assertIsInstance(provider, LlamaParseProvider)
        self.assertEqual(
            ["llama_parse", "llama_parse_advanced"],
            [
                yaml.safe_load((plugin_root / tool).read_text())["identity"]["name"]
                for tool in declared_tools
            ],
        )


if __name__ == "__main__":
    unittest.main()
