from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "qwen-image.py"
SPEC = importlib.util.spec_from_file_location("qwen_image", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
qwen_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qwen_image)

build_payload = qwen_image.build_payload
endpoint_path = qwen_image.endpoint_path
extract_images = qwen_image.extract_images
download_protected_image = qwen_image.download_protected_image


class QwenImagePayloadTests(unittest.TestCase):
    def test_image_3_models_use_unified_image_endpoint(self) -> None:
        for model in ("qwen-image-3.0", "qwen-image-3.0-pro"):
            with self.subTest(model=model):
                self.assertEqual(endpoint_path(model), "/ai/v1/images/generations")

    def test_image_3_payload_uses_top_level_openai_shape(self) -> None:
        payload = build_payload(
            model="qwen-image-3.0",
            prompt="draw a circle",
            resolution="1024x1024",
            num_images=1,
            refer_image="",
            guidance=7.5,
            watermark=False,
            image_format="png",
        )

        self.assertNotIn("input", payload)
        self.assertEqual(payload["model"], "qwen-image-3.0")
        self.assertEqual(payload["prompt"], "draw a circle")
        self.assertEqual(payload["size"], "1024x1024")
        self.assertEqual(payload["output_format"], "png")
        self.assertNotIn("watermark", payload)
        self.assertNotIn("extra", payload)

    def test_image_3_watermark_uses_vendor_extra(self) -> None:
        payload = build_payload(
            model="qwen-image-3.0-pro",
            prompt="draw a circle",
            resolution="1024x1024",
            num_images=1,
            refer_image="",
            guidance=7.5,
            watermark=True,
            image_format="png",
        )

        self.assertNotIn("watermark", payload)
        self.assertEqual(payload["extra"], {"watermark": True})

    def test_existing_models_keep_predictions_shape(self) -> None:
        payload = build_payload(
            model="qwen-image-2.0-pro",
            prompt="draw a circle",
            resolution="1024x1024",
            num_images=1,
            refer_image="",
            guidance=7.5,
            watermark=False,
            image_format="png",
        )

        self.assertEqual(
            endpoint_path("qwen-image-2.0-pro"),
            "/v1/models/bailian/qwen-image-2.0-pro/predictions",
        )
        self.assertEqual(payload["input"]["prompt"], "draw a circle")
        self.assertNotIn("model", payload)

    def test_extract_images_supports_unified_and_legacy_responses(self) -> None:
        self.assertEqual(
            extract_images({"data": [{"url": "https://example.com/image.png"}]}),
            [{"url": "https://example.com/image.png"}],
        )
        self.assertEqual(
            extract_images({"output": [{"bytesBase64": "encoded-image"}]}),
            [{"b64_json": "encoded-image"}],
        )
        self.assertEqual(
            extract_images(
                {
                    "output": [
                        {
                            "content_url": "https://example.com/ai/v1/images/task/content/result"
                        }
                    ]
                }
            ),
            [
                {
                    "content_url": "https://example.com/ai/v1/images/task/content/result"
                }
            ],
        )

    def test_protected_result_download_reuses_api_key(self) -> None:
        response = Mock(status_code=200, content=b"image-bytes")
        with patch.object(qwen_image.requests, "get", return_value=response) as get:
            self.assertEqual(
                download_protected_image("https://example.com/result", "test-key"),
                b"image-bytes",
            )

        get.assert_called_once_with(
            "https://example.com/result",
            headers={"Authorization": "Bearer test-key"},
            timeout=120,
        )

    def test_protected_result_download_rejects_http_error(self) -> None:
        response = Mock(status_code=401, content=b"")
        with patch.object(qwen_image.requests, "get", return_value=response):
            with self.assertRaisesRegex(
                qwen_image.InvokeError,
                "result download failed with status 401",
            ):
                download_protected_image("https://example.com/result", "test-key")

    def test_image_3_invoke_downloads_protected_output_as_blob(self) -> None:
        post_response = Mock(status_code=200)
        post_response.json.return_value = {
            "id": "task-123",
            "status": "completed",
            "output": [
                {
                    "content_url": "https://example.com/ai/v1/images/task/content/result"
                }
            ],
        }
        get_response = Mock(status_code=200, content=b"\x89PNG\r\n\x1a\nimage")
        tool = qwen_image.QwenImageTool(
            runtime=Mock(
                credentials={
                    "api_key": "test-key",
                    "base_url": "https://example.com",
                }
            ),
            session=Mock(),
        )

        with (
            patch.object(qwen_image.requests, "post", return_value=post_response) as post,
            patch.object(qwen_image.requests, "get", return_value=get_response) as get,
        ):
            messages = list(
                tool._invoke(
                    {
                        "model": "qwen-image-3.0-pro",
                        "prompt": "red dot",
                        "resolution": "1024x1024",
                        "num_images": 1,
                        "image_format": "png",
                    }
                )
            )

        post.assert_called_once()
        self.assertEqual(
            post.call_args.args[0],
            "https://example.com/ai/v1/images/generations",
        )
        get.assert_called_once_with(
            "https://example.com/ai/v1/images/task/content/result",
            headers={"Authorization": "Bearer test-key"},
            timeout=120,
        )
        self.assertEqual(messages[1].message.blob, get_response.content)
        self.assertEqual(messages[2].message.json_object["task_id"], "task-123")


if __name__ == "__main__":
    unittest.main()
