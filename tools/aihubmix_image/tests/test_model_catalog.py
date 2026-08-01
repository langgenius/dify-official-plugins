from __future__ import annotations

import unittest
from pathlib import Path

import yaml


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def read_yaml(relative: str) -> dict:
    return yaml.safe_load((PLUGIN_ROOT / relative).read_text(encoding="utf-8"))


def parameter(data: dict, name: str) -> dict | None:
    return next((item for item in data.get("parameters", []) if item.get("name") == name), None)


def option_values(rule: dict | None) -> list[str]:
    if not rule:
        return []
    return [str(item["value"]) for item in rule.get("options", [])]


class ImageModelCatalogTests(unittest.TestCase):
    def test_provider_registers_new_model_tools(self) -> None:
        provider = read_yaml("provider/aihubmix-image.yaml")
        self.assertIn("tools/gemini-3-1-flash-lite-image.yaml", provider["tools"])
        self.assertIn("tools/mai-image.yaml", provider["tools"])
        self.assertIn("tools/doubao-seedream-5-pro.yaml", provider["tools"])

    def test_gemini_tool_contains_stable_models_and_only_sdk_ratios(self) -> None:
        data = read_yaml("tools/gemini-3-pro-image-preview.yaml")
        models = option_values(parameter(data, "model"))
        ratios = option_values(parameter(data, "aspect_ratio"))

        self.assertIn("gemini-3-pro-image", models)
        self.assertIn("gemini-3.1-flash-image", models)
        self.assertNotIn("4:5", ratios)
        self.assertNotIn("5:4", ratios)
        self.assertIsNone(parameter(data, "image_format"))

    def test_lite_tool_exposes_only_verified_1k_resolution(self) -> None:
        data = read_yaml("tools/gemini-3-1-flash-lite-image.yaml")
        self.assertEqual(option_values(parameter(data, "model")), ["gemini-3.1-flash-lite-image"])
        self.assertEqual(option_values(parameter(data, "resolution")), ["1K"])
        self.assertIsNone(parameter(data, "image_format"))

    def test_mai_tool_contains_both_verified_models_and_no_unverified_controls(self) -> None:
        data = read_yaml("tools/mai-image.yaml")
        self.assertEqual(
            option_values(parameter(data, "model")),
            ["mai-image-2.5-flash", "mai-image-2.5"],
        )
        self.assertEqual(
            [item["name"] for item in data["parameters"]],
            ["prompt", "model"],
        )

    def test_shared_doubao_tool_excludes_pro_model(self) -> None:
        data = read_yaml("tools/doubao.yaml")
        self.assertNotIn("doubao-seedream-5.0-pro", option_values(parameter(data, "model")))

    def test_doubao_pro_tool_exposes_only_verified_parameters(self) -> None:
        relative = "tools/doubao-seedream-5-pro.yaml"
        self.assertTrue((PLUGIN_ROOT / relative).is_file())

        data = read_yaml(relative)
        self.assertEqual(
            [item["name"] for item in data["parameters"]],
            [
                "prompt",
                "model",
                "generation_mode",
                "reference_image",
                "image_strength",
                "size",
                "response_format",
                "watermark",
            ],
        )
        self.assertEqual(
            option_values(parameter(data, "model")),
            ["doubao-seedream-5.0-pro"],
        )
        self.assertEqual(option_values(parameter(data, "size")), ["1K", "2K"])
        self.assertEqual(
            option_values(parameter(data, "generation_mode")),
            ["text_to_image", "image_to_image"],
        )
        self.assertEqual(option_values(parameter(data, "response_format")), ["url", "b64_json"])
        self.assertEqual(data["extra"]["python"]["source"], "tools/doubao.py")


if __name__ == "__main__":
    unittest.main()
