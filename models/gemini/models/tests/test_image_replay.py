import base64
import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    UserPromptMessage,
)
from google import genai
from google.genai import types
from models.llm.llm import GoogleLargeLanguageModel


MODEL = "gemini-nano-banana-2.1"


@pytest.mark.parametrize("stream", [False, True])
def test_generated_images_fit_in_one_frame_and_replay_in_order(stream):
    # A 2 MiB image fits in the daemon's 5 MiB frame limit when sent once.
    first = base64.b64encode(b"first image bytes" * 131072).decode()
    second = base64.b64encode(b"second image bytes").decode()
    draft = base64.b64encode(b"internal draft").decode()
    parts = [
        {"inlineData": {"mimeType": "image/png", "data": draft}, "thought": True},
        {"text": "First", "thoughtSignature": "AAE="},
        {
            "inlineData": {"mimeType": "image/png", "data": first},
            "thoughtSignature": "/wE=",
        },
        {"text": "Second"},
        {
            "inlineData": {"mimeType": "image/png", "data": second},
            "thoughtSignature": "/wI=",
        },
    ]
    expected = types.Content.model_validate({"role": "model", "parts": parts})
    prompt = UserPromptMessage(content="Draw two images.")
    schema = Path(__file__).parents[1] / "llm" / f"{MODEL}.yaml"
    llm = GoogleLargeLanguageModel(
        [AIModelEntity(**yaml.safe_load(schema.read_text()))]
    )
    requests = []

    def completion(output_parts):
        return {
            "candidates": [
                {
                    "content": {"role": "model", "parts": output_parts},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 100},
        }

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 2:
            assert types.Content.model_validate(body["contents"][1]) == expected
            return httpx.Response(200, json=completion([{"text": "Done"}]))
        if not stream:
            return httpx.Response(200, json=completion(parts))
        chunks = [
            {"candidates": [{"content": {"role": "model", "parts": chunk}}]}
            for chunk in (parts[:2], parts[2:3], parts[3:])
        ]
        chunks.append(completion([]))
        return httpx.Response(
            200, text="".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
        )

    with (
        genai.Client(
            api_key="offline",
            http_options=types.HttpOptions(
                client_args={
                    "transport": httpx.MockTransport(transport),
                    "trust_env": False,
                },
                async_client_args={"trust_env": False},
            ),
        ) as client,
        patch("models.llm.llm.genai.Client", return_value=client),
    ):
        credentials = {"google_api_key": "offline", "file_url": "https://files.invalid"}
        frames = [
            chunk.model_dump_json()
            for chunk in llm.invoke(
                MODEL, credentials, [prompt], {"include_thoughts": True}, stream=stream
            )
        ]
        assert all(len(frame.encode()) < 5 * 1024**2 for frame in frames)
        assert sum(frame.count(first) for frame in frames) == 1
        assert sum(frame.count(second) for frame in frames) == 1

        assistant = AssistantPromptMessage(content=[])
        for frame in frames:
            delta = LLMResultChunk.model_validate_json(frame).delta.message
            assistant.content.extend(delta.content)
            if delta.opaque_body is not None:
                assistant.opaque_body = delta.opaque_body
        visible = [
            item
            for item in assistant.content
            if isinstance(item, ImagePromptMessageContent)
        ]
        assert [img.base64_data for img in visible] == [first, second]
        if stream:
            # Dify can replace a returned image's bytes with a file URL in history.
            visible[1].base64_data = ""
            visible[1].url = "/files/second.png"
        with patch(
            "models.llm.file_parts.requests.get",
            return_value=Mock(content=base64.b64decode(second)),
        ) as fetch:
            history = [prompt, assistant, UserPromptMessage(content="Edit both.")]
            list(llm.invoke(MODEL, credentials, history, stream=False))
            assert fetch.call_count == int(stream)
    assert len(requests) == 2


def test_legacy_snapshot_can_supply_its_own_image():
    part = types.Part(
        inline_data=types.Blob(data=b"original", mime_type="image/png"),
        thought_signature=b"\xff",
    )
    original = types.Content(role="model", parts=[part])
    message = AssistantPromptMessage(
        content="",
        opaque_body={
            "gemini_content": original.model_dump(mode="json", exclude_none=True)
        },
    )
    llm = GoogleLargeLanguageModel([])
    assert llm._build_gemini_contents(
        [message], Mock(), types.GenerateContentConfig()
    ) == [original]
