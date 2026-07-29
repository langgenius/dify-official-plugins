from __future__ import annotations

import unittest

from dify_plugin.errors.model import InvokeError

from tools import doubao
from tools.doubao import build_input_payload


class DoubaoPayloadTests(unittest.TestCase):
    def test_pro_model_omits_unsupported_sequential_fields(self) -> None:
        payload = build_input_payload(
            model="doubao-seedream-5.0-pro",
            prompt="draw a square",
            size="2K",
            stream=False,
            response_format="url",
            watermark=True,
            generation_mode="text_to_image",
            sequential_image_generation="disabled",
            max_sequential_images=4,
        )

        self.assertNotIn("sequential_image_generation", payload)
        self.assertNotIn("sequential_image_generation_options", payload)

    def test_pro_model_rejects_streaming_before_request(self) -> None:
        with self.assertRaises(InvokeError):
            build_input_payload(
                model="doubao-seedream-5.0-pro",
                prompt="draw a square",
                size="1K",
                stream=True,
                response_format="url",
                watermark=False,
                generation_mode="text_to_image",
                sequential_image_generation="disabled",
                max_sequential_images=4,
            )

    def test_pro_model_rejects_unverified_4k_size_before_request(self) -> None:
        with self.assertRaises(InvokeError):
            build_input_payload(
                model="doubao-seedream-5.0-pro",
                prompt="draw a square",
                size="4K",
                stream=False,
                response_format="url",
                watermark=False,
                generation_mode="text_to_image",
                sequential_image_generation="disabled",
                max_sequential_images=4,
            )

    def test_lite_model_keeps_supported_sequential_fields(self) -> None:
        payload = build_input_payload(
            model="doubao-seedream-5.0-lite",
            prompt="draw a square",
            size="2K",
            stream=False,
            response_format="url",
            watermark=True,
            generation_mode="sequential",
            sequential_image_generation="enabled",
            max_sequential_images=4,
        )

        self.assertEqual(payload["sequential_image_generation"], "enabled")
        self.assertEqual(payload["sequential_image_generation_options"], {"max_images": 4})

    def test_extract_images_maps_gateway_bytes_base64(self) -> None:
        extract_images = getattr(doubao, "extract_images", None)
        self.assertIsNotNone(extract_images)
        self.assertEqual(
            extract_images({"output": [{"bytesBase64": "encoded-jpeg"}]}),
            [{"b64_json": "encoded-jpeg"}],
        )

    def test_detect_image_format_uses_file_signatures(self) -> None:
        detect_image_format = getattr(doubao, "detect_image_format", None)
        self.assertIsNotNone(detect_image_format)

        cases = [
            (b"\xff\xd8\xff\xe0jpeg", ("image/jpeg", "jpg")),
            (b"\x89PNG\r\n\x1a\npng", ("image/png", "png")),
            (b"RIFF\x00\x00\x00\x00WEBPwebp", ("image/webp", "webp")),
        ]
        for image_bytes, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(detect_image_format(image_bytes), expected)


if __name__ == "__main__":
    unittest.main()
