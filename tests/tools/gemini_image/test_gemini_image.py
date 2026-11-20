import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


source = (
    Path(__file__).resolve().parents[3] / "tools/gemini_image/tools/image_generate.py"
)
spec = importlib.util.spec_from_file_location("gemini_image_generate", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("count", [0, 14, 15])
def test_nano_banana_generates_and_edits_with_reference_limits(monkeypatch, count):
    tool = Mock()
    tool.runtime.credentials = {"gemini_api_key": "test"}
    response = Mock()
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "interim"},
                        {"text": "Done"},
                        {"inlineData": {"mimeType": "image/jpeg", "data": "aW1hZ2U="}},
                    ]
                }
            }
        ]
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(module.requests, "post", post)
    params = {
        "model": "gemini-nano-banana-2.1",
        "prompt": "A garden",
        "image_size": "4K",
        "aspect_ratio": "8:1",
        "images": [SimpleNamespace(blob=b"ref", mime_type="image/png")] * count,
    }
    list(module.ImageGenerateTool._invoke(tool, params))
    if count > 14:
        post.assert_not_called()
        tool.create_text_message.assert_called_once_with(
            "Use at most 14 reference images."
        )
        return
    assert post.call_args.args[0].endswith(
        "/v1/models/gemini-nano-banana-2.1:generateContent"
    )
    body = post.call_args.kwargs["json"]
    assert body["generationConfig"]["imageConfig"] == {
        "imageSize": "4K",
        "aspectRatio": "8:1",
    }
    assert len(body["contents"][0]["parts"]) == count + 1
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "test"
    tool.create_text_message.assert_called_once_with(text="Done")
    tool.create_blob_message.assert_called_once_with(
        blob=b"image", meta={"filename": "output0.jpeg", "mime_type": "image/jpeg"}
    )
