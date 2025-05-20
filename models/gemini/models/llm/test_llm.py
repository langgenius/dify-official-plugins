import base64
import dataclasses
from typing import Sequence

import pytest

from .llm import _content_to_part, GoogleLargeLanguageModel
from dify_plugin.entities.model.message import (
    PromptMessage,
    UserPromptMessage,
    ToolPromptMessage,
    AssistantPromptMessage,
    SystemPromptMessage,
    PromptMessageContent,
    MultiModalPromptMessageContent,
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import     InvokeError
from google.genai import types


@dataclasses.dataclass(frozen=True)
class TestCase:
    message: PromptMessageContent
    expected: types.Part


class TestContentToParts:
    def test_text_content(self):
        message=TextPromptMessageContent(
                data="Test text content"
            )
        assert _content_to_part(message) == types.Part.from_text(text="Test text content"), "TextPromptMessageContent should be converted to text Part."
    
    def test_multimodal_contents_with_url(self):
        cases = [
            TestCase(
                message=ImagePromptMessageContent(
                    format='jpeg',
                    url="https://example.com/image.jpg",
                    mime_type="image/jpeg"
                ),
                expected=types.Part.from_uri(
                    file_uri="https://example.com/image.jpg",
                    mime_type="image/jpeg"
                )
            ),
            TestCase(
                message=AudioPromptMessageContent(
                    format='mp3',
                    url="https://example.com/audio.mp3",
                    mime_type="audio/mpeg"
                ),
                expected=types.Part.from_uri(
                    file_uri="https://example.com/audio.mp3",
                    mime_type="audio/mpeg"
                )
            ),
            TestCase(
                message=VideoPromptMessageContent(
                    format='mp4',
                    url="https://example.com/video.mp4",
                    mime_type="video/mp4"
                ),
                expected=types.Part.from_uri(
                    file_uri="https://example.com/video.mp4",
                    mime_type="video/mp4"
                ),
            ),
            TestCase(
                message=DocumentPromptMessageContent(
                    format='pdf',
                    url="https://example.com/document.pdf",
                    mime_type="application/pdf",
                ),
                expected=types.Part.from_uri(
                    file_uri="https://example.com/document.pdf",
                    mime_type="application/pdf"
                ),
            )
        ]

        for idx, c in enumerate(cases):
            assert _content_to_part(c.message) == c.expected, f"Test case {idx+1} failed, type: {type(c.message)}"

    def test_multimodal_contents_with_base64(self):
        binary_data = b'Test base64'
        base64_data = base64.b64encode(binary_data).decode()

        cases = [
            TestCase(
                message=ImagePromptMessageContent(
                    format='jpeg',
                    base64_data=base64_data,
                    mime_type="image/jpeg"
                ),
                expected=types.Part.from_bytes(
                    data=binary_data,
                    mime_type="image/jpeg"
                )
            ),
            TestCase(
                message=AudioPromptMessageContent(
                    format='mp3',
                    base64_data=base64_data,
                    mime_type="audio/mpeg"
                ),
                expected=types.Part.from_bytes(
                    data=binary_data,
                    mime_type="audio/mpeg"
                )
            ),
            TestCase(
                message=VideoPromptMessageContent(
                    format='mp4',
                    base64_data=base64_data,
                    mime_type="video/mp4"
                ),
                expected=types.Part.from_bytes(
                    data=binary_data,
                    mime_type="video/mp4"
                ),
            ),
            TestCase(
                message=DocumentPromptMessageContent(
                    format='pdf',
                    base64_data=base64_data,
                    mime_type="application/pdf",
                ),
                expected=types.Part.from_bytes(
                    data=binary_data,
                    mime_type="application/pdf"
                ),
            )
        ]

        for idx, c in enumerate(cases, start=1):
            assert _content_to_part(c.message) == c.expected, f"Test case {idx} failed, type: {type(c.message)}"

    def test_unknown_content_type(self):
        cases = [
            PromptMessageContent(),
            MultiModalPromptMessageContent(
                format="fake",
                mime_type="text/plain",
                base64_data="",
            ),
            "",
        ]

        for idx, c in enumerate(cases, start=1):
            with pytest.raises(InvokeError) as exc:
                _content_to_part(c)
            assertion_msg = f"Test case {idx} failed, type: {type(c)}"
            assert "unknown content type" in exc.value.args[0], assertion_msg


class TestConvertToContents:
    def test_convert_to_contents(self):
        prompt_msgs: list[PromptMessage] = [
            SystemPromptMessage(content="System Prompt 1"),
            UserPromptMessage(content="User Prompt 1"),
            UserPromptMessage(content="User Prompt 2"),
            AssistantPromptMessage(content="Assistant Prompt 1"),
            UserPromptMessage(content="User Prompt 3"),
            ToolPromptMessage(tool_call_id="test-tool", content="Tool Prompt 1"),
            UserPromptMessage(content="User Prompt 4"),
        ]
        # TODO(QuantumGhost): The type hint is inaccurate.
        expected: list[types.ContentDict] = [
            types.ContentDict(
                parts=[
                    types.Part(text="User Prompt 1"),
                    types.Part(text="User Prompt 2"),
                ],
                role="user",
            ),
            types.ContentDict(
                parts=[
                    types.Part(text="Assistant Prompt 1"),
                ],
                role="model",
            ),
            types.ContentDict(
                parts=[
                    types.Part(text="User Prompt 3"),
                ],
                role="user",
            ),
            types.ContentDict(
                parts=[
                    types.Part(text="Tool Prompt 1"), 
                ],
                role="model",
            ),
            types.ContentDict(
                parts=[
                    types.Part(text="User Prompt 4"),
                ],
                role="user",
            ),
        ]
        
        instance = GoogleLargeLanguageModel([])
        result = instance._convert_to_contents(prompt_msgs)
        assert result == expected
        assert instance._convert_to_contents([]) == []


def test_file_url():
    credentials = {
        "file_url": "http://127.0.0.1/static/"
    }
    message_content = MultiModalPromptMessageContent(
        format="png",
        mime_type='image/png',
        url="http://127.0.0.1:5001/files/foo/bar.png"
    )
    file_url = f"{credentials["file_url"].rstrip('/')}/files{message_content.url.split("/files")[-1]}"
    assert file_url == "http://127.0.0.1/static/files/foo/bar.png"
