import base64
import dataclasses
import time
from unittest.mock import Mock, patch

import pytest

from models.llm.llm import GoogleLargeLanguageModel
from dify_plugin.entities.model.message import (
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
from google.genai import types


@dataclasses.dataclass(frozen=True)
class ContentCase:
    message: PromptMessageContent
    expected: types.Part


class TestContentConversion:
    """Test suite for content conversion following the original test design philosophy"""

    def setup_method(self):
        """Setup test fixtures"""
        self.llm = GoogleLargeLanguageModel([])
        self.mock_config = types.GenerateContentConfig()

        # Setup mock client for file uploads
        self.mock_client = Mock()
        self.mock_file = Mock()
        self.mock_file.uri = "gs://test-bucket/test-file"
        self.mock_file.mime_type = "image/jpeg"
        self.mock_file.state.name = "ACTIVE"
        self.mock_client.files.upload.return_value = self.mock_file
        self.mock_client.files.get.return_value = self.mock_file

    def test_text_content(self):
        """Test that TextPromptMessageContent is converted to text Part"""
        message = UserPromptMessage(content=[TextPromptMessageContent(data="Test text content")])

        contents = self.llm._build_gemini_contents(
            prompt_messages=[message], genai_client=self.mock_client, config=self.mock_config
        )

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "Test text content"
        assert contents[0].parts[0] == types.Part.from_text(text="Test text content")

    def test_multimodal_contents_with_url(self):
        """Test multimodal content types with URLs"""
        # Using localhost URLs that would be typical in a Dify deployment
        cases = [
            ContentCase(
                message=ImagePromptMessageContent(
                    format="jpeg",
                    url="http://localhost:5001/files/images/test.jpg",
                    mime_type="image/jpeg",
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="image/jpeg"
                ),
            ),
            ContentCase(
                message=AudioPromptMessageContent(
                    format="mp3",
                    url="http://localhost:5001/files/audio/test.mp3",
                    mime_type="audio/mpeg",
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="audio/mpeg"
                ),
            ),
            ContentCase(
                message=VideoPromptMessageContent(
                    format="mp4",
                    url="http://localhost:5001/files/video/test.mp4",
                    mime_type="video/mp4",
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="video/mp4"
                ),
            ),
            ContentCase(
                message=DocumentPromptMessageContent(
                    format="pdf",
                    url="http://localhost:5001/files/documents/test.pdf",
                    mime_type="application/pdf",
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="application/pdf"
                ),
            ),
        ]

        for idx, c in enumerate(cases):
            # Update mock for correct mime type
            self.mock_file.mime_type = c.message.mime_type

            with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"), patch(
                "requests.get"
            ) as mock_get:
                mock_response = Mock()
                mock_response.content = b"test content"
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response

                user_message = UserPromptMessage(content=[c.message])
                contents = self.llm._build_gemini_contents(
                    prompt_messages=[user_message],
                    genai_client=self.mock_client,
                    config=self.mock_config,
                )

                assert len(contents) == 1, f"Test case {idx + 1} failed, type: {type(c.message)}"
                assert contents[0].role in ["user"]
                assert len(contents[0].parts) == 1
                assert contents[0].parts[0].file_data.file_uri == c.expected.file_data.file_uri
                assert contents[0].parts[0].file_data.mime_type == c.expected.file_data.mime_type

    def test_multimodal_contents_with_base64(self):
        """Test multimodal content types with base64 data"""
        binary_data = b"Test base64"
        base64_data = base64.b64encode(binary_data).decode()

        cases = [
            ContentCase(
                message=ImagePromptMessageContent(
                    format="jpeg", base64_data=base64_data, mime_type="image/jpeg"
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="image/jpeg"
                ),
            ),
            ContentCase(
                message=AudioPromptMessageContent(
                    format="mp3", base64_data=base64_data, mime_type="audio/mpeg"
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="audio/mpeg"
                ),
            ),
            ContentCase(
                message=VideoPromptMessageContent(
                    format="mp4", base64_data=base64_data, mime_type="video/mp4"
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="video/mp4"
                ),
            ),
            ContentCase(
                message=DocumentPromptMessageContent(
                    format="pdf", base64_data=base64_data, mime_type="application/pdf"
                ),
                expected=types.Part.from_uri(
                    file_uri="gs://test-bucket/test-file", mime_type="application/pdf"
                ),
            ),
        ]

        for idx, c in enumerate(cases, start=1):
            # Update mock for correct mime type
            self.mock_file.mime_type = c.message.mime_type

            with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):
                user_message = UserPromptMessage(content=[c.message])
                contents = self.llm._build_gemini_contents(
                    prompt_messages=[user_message],
                    genai_client=self.mock_client,
                    config=self.mock_config,
                )

                assert len(contents) == 1, f"Test case {idx} failed, type: {type(c.message)}"
                assert contents[0].role == "user"
                assert len(contents[0].parts) == 1
                # After upload, content becomes a file URI part
                assert contents[0].parts[0].file_data.file_uri == c.expected.file_data.file_uri
                assert contents[0].parts[0].file_data.mime_type == c.expected.file_data.mime_type

    def test_mixed_content_types(self):
        """Test message with mixed text and multimodal content"""
        binary_data = b"Test image"
        base64_data = base64.b64encode(binary_data).decode()

        user_message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Look at this image:"),
                ImagePromptMessageContent(
                    format="png", base64_data=base64_data, mime_type="image/png"
                ),
                TextPromptMessageContent(data="What do you see?"),
            ]
        )

        self.mock_file.mime_type = "image/png"

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):
            contents = self.llm._build_gemini_contents(
                prompt_messages=[user_message],
                genai_client=self.mock_client,
                config=self.mock_config,
            )

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 3
        assert contents[0].parts[0].text == "Look at this image:"
        assert contents[0].parts[1].file_data.file_uri == "gs://test-bucket/test-file"
        assert contents[0].parts[2].text == "What do you see?"

    def test_invalid_message_type(self):
        """Test that invalid message types raise appropriate errors"""
        # Create a mock invalid message type
        invalid_message = Mock(spec=[])
        invalid_message.content = "test"

        with pytest.raises(ValueError, match="Unknown message type"):
            self.llm._format_message_to_gemini_content(
                message=invalid_message, genai_client=self.mock_client, config=self.mock_config
            )

    def test_file_upload_with_caching(self):
        """Test that file uploads are cached properly"""
        binary_data = b"Test data for caching"
        base64_data = base64.b64encode(binary_data).decode()

        message_content = ImagePromptMessageContent(
            format="jpeg", base64_data=base64_data, mime_type="image/jpeg"
        )

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):
            # First upload
            uri1, mime1 = self.llm._upload_file_content_to_google(message_content, self.mock_client)

            # Second upload (should use cache)
            uri2, mime2 = self.llm._upload_file_content_to_google(message_content, self.mock_client)

            assert uri1 == uri2 == "gs://test-bucket/test-file"
            assert mime1 == mime2 == "image/jpeg"
            # File upload should only be called once due to caching
            assert self.mock_client.files.upload.call_count == 1

    def test_file_url_with_prefix(self):
        """Test file URL handling with server prefix"""
        message_content = DocumentPromptMessageContent(
            format="pdf", url="/files/doc.pdf", mime_type="application/pdf"
        )

        self.mock_file.mime_type = "application/pdf"

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"), patch(
            "requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.content = b"PDF content"
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            uri, mime = self.llm._upload_file_content_to_google(
                message_content, self.mock_client, file_server_url_prefix="https://api.example.com"
            )

            # Check that the URL was constructed correctly
            mock_get.assert_called_once_with("https://api.example.com/files/doc.pdf")
            assert uri == "gs://test-bucket/test-file"
            assert mime == "application/pdf"

    def test_invalid_url_without_prefix(self):
        """Test that invalid URLs without proper prefix raise errors"""
        message_content = ImagePromptMessageContent(
            format="jpeg", url="/relative/path/image.jpg", mime_type="image/jpeg"
        )

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):
            with pytest.raises(ValueError, match="Set FILES_URL env first!"):
                self.llm._upload_file_content_to_google(message_content, self.mock_client)


def test_file_url():
    credentials = {"file_url": "http://127.0.0.1/static/"}
    message_content = MultiModalPromptMessageContent(
        format="png", mime_type="image/png", url="http://127.0.0.1:5001/files/foo/bar.png"
    )
    file_url = (
        f"{credentials['file_url'].rstrip('/')}/files{message_content.url.split('/files')[-1]}"
    )
    assert file_url == "http://127.0.0.1/static/files/foo/bar.png"


class TestBuildGeminiContents:
    """Test suite for the _build_gemini_contents method"""

    def setup_method(self):
        """Setup test fixtures"""
        self.llm = GoogleLargeLanguageModel([])
        self.mock_client = None  # Will be mocked in tests that need it
        self.mock_config = types.GenerateContentConfig()

    def test_simple_user_message(self):
        """Test conversion of a simple user message"""
        messages = [UserPromptMessage(content="Hello, how are you?")]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "Hello, how are you?"

    def test_assistant_message_with_text(self):
        """Test conversion of assistant message with text content"""
        messages = [AssistantPromptMessage(content="I'm doing well, thank you!")]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        assert len(contents) == 1
        assert contents[0].role == "model"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "I'm doing well, thank you!"

    def test_assistant_message_with_thinking_tags(self):
        """Test that thinking tags are properly removed from assistant messages"""
        messages = [
            AssistantPromptMessage(
                content="<think>This is internal thinking that should be removed</think>This is the actual response"
            )
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        assert len(contents) == 1
        assert contents[0].role == "model"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "This is the actual response"

    def test_system_message_as_instruction(self):
        """Test that system messages with string content are set as system instruction"""
        messages = [
            SystemPromptMessage(content="You are a helpful assistant"),
            UserPromptMessage(content="Hello"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # System message should set config.system_instruction, not appear in contents
        assert self.mock_config.system_instruction == "You are a helpful assistant"
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Hello"

    def test_system_message_with_multimodal_content(self):
        """Test that system messages with list content are converted to user messages"""
        messages = [
            SystemPromptMessage(
                content=[
                    TextPromptMessageContent(data="System context with image:"),
                    ImagePromptMessageContent(
                        format="png",
                        base64_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
                        mime_type="image/png",
                    ),
                ]
            )
        ]

        # Mock the file upload since we have multimodal content
        from unittest.mock import Mock, patch

        mock_client = Mock()
        mock_file = Mock()
        mock_file.uri = "gs://test-file-uri"
        mock_file.mime_type = "image/png"
        mock_file.state.name = "ACTIVE"
        mock_client.files.upload.return_value = mock_file
        mock_client.files.get.return_value = mock_file

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):
            contents = self.llm._build_gemini_contents(
                prompt_messages=messages, genai_client=mock_client, config=self.mock_config
            )

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "System context with image:"
        assert contents[0].parts[1].file_data.file_uri == "gs://test-file-uri"

    def test_tool_message(self):
        """Test conversion of tool prompt messages"""
        messages = [
            ToolPromptMessage(
                name="get_weather",
                content="The weather is sunny and 72°F",
                tool_call_id=f"get_weather_{int(time.time())}",
            )
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].function_response.name == "get_weather"
        assert contents[0].parts[0].function_response.response == {
            "response": "The weather is sunny and 72°F"
        }

    def test_assistant_message_with_tool_calls(self):
        """Test conversion of assistant messages with tool calls"""
        messages = [
            AssistantPromptMessage(
                content="I'll check the weather for you",
                tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id="call_123",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="get_weather", arguments='{"location": "New York"}'
                        ),
                    )
                ],
            )
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        assert len(contents) == 1
        assert contents[0].role == "model"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "I'll check the weather for you"
        assert contents[0].parts[1].function_call.name == "get_weather"
        assert contents[0].parts[1].function_call.args == {"location": "New York"}

    def test_role_alternation_merging(self):
        """Test that consecutive messages with the same role are merged"""
        messages = [
            UserPromptMessage(content="First user message"),
            UserPromptMessage(content="Second user message"),
            AssistantPromptMessage(content="Assistant response"),
            UserPromptMessage(content="Third user message"),
            UserPromptMessage(content="Fourth user message"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # Should have 3 contents after merging consecutive user messages
        assert len(contents) == 3

        # First content: merged user messages
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "First user message"
        assert contents[0].parts[1].text == "Second user message"

        # Second content: assistant message
        assert contents[1].role == "model"
        assert len(contents[1].parts) == 1
        assert contents[1].parts[0].text == "Assistant response"

        # Third content: merged user messages
        assert contents[2].role == "user"
        assert len(contents[2].parts) == 2
        assert contents[2].parts[0].text == "Third user message"
        assert contents[2].parts[1].text == "Fourth user message"

    def test_mixed_message_types_with_role_merging(self):
        """Test complex conversation with mixed message types and role merging"""
        tool_id = "gemini_call_current_time_1754935692572538600"
        messages = [
            SystemPromptMessage(content="You are a helpful assistant"),
            UserPromptMessage(content="Hello"),
            AssistantPromptMessage(content="Hello! How can I help you?"),
            UserPromptMessage(content=[TextPromptMessageContent(data="Get current time")]),
            AssistantPromptMessage(
                content="Yes, I can help you",
                tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id=tool_id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="current_time", arguments="{}"
                        ),
                    )
                ],
            ),
            ToolPromptMessage(
                name="current_time", content="2025-08-12 02:08:12", tool_call_id=tool_id
            ),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # System message sets instruction, not in contents
        assert self.mock_config.system_instruction == "You are a helpful assistant"

        # Should have 5 contents after processing
        assert len(contents) == 5

        # First: merged user messages
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "Hello"

        # Second: assistant message
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "Hello! How can I help you?"

        # Third: tool message (becomes user role)
        assert contents[2].role == "user"
        assert contents[2].parts[0].text == "Get current time"
        assert len(contents[2].parts) == 1

        # Fourth: final user message
        assert contents[3].role == "model"
        assert contents[3].parts[0].text == "Yes, I can help you"
        assert not contents[3].parts[0].function_call
        assert contents[3].parts[1].function_call.name == "current_time"
        assert contents[3].parts[1].function_call.args == {}

        assert contents[4].role == "user"
        assert contents[4].parts[0].function_response.name == "current_time"
        _r = contents[4].parts[0].function_response.response.get("response")
        assert _r == "2025-08-12 02:08:12"

    def test_empty_message_list(self):
        """Test handling of empty message list"""
        contents = self.llm._build_gemini_contents(
            prompt_messages=[], genai_client=self.mock_client, config=self.mock_config
        )

        assert contents == []

    def test_message_with_empty_content(self):
        """Test handling of messages with empty content

        In Gemini message history, both empty parts list and empty string text parts
        for model messages are valid and won't cause communication errors.
        """
        # Test case 1: Assistant message with empty string content
        messages = [AssistantPromptMessage(content=""), UserPromptMessage(content="Hello")]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # Empty string content creates an empty parts list, which is valid for Gemini
        assert len(contents) == 2
        assert contents[0].role == "model"
        assert contents[0].parts == []  # Empty parts list is valid
        assert contents[1].role == "user"
        assert contents[1].parts[0].text == "Hello"

        # Test case 2: Assistant message with only thinking tags (results in empty content after removal)
        messages = [
            AssistantPromptMessage(content="<think>Internal thoughts only</think>"),
            UserPromptMessage(content="Hi"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # After removing thinking tags, content is empty - creates empty parts list
        assert len(contents) == 2
        assert contents[0].role == "model"
        assert contents[0].parts == []  # Empty parts list after thinking tag removal
        assert contents[1].role == "user"
        assert contents[1].parts[0].text == "Hi"

        # Test case 3: Mixed empty and non-empty assistant messages
        messages = [
            UserPromptMessage(content="Question"),
            AssistantPromptMessage(content=""),
            AssistantPromptMessage(content="Actual response"),
            UserPromptMessage(content="Thanks"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # Should have 3 contents - consecutive assistant messages are merged
        assert len(contents) == 3
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Question"
        assert contents[1].role == "model"
        assert (
            len(contents[1].parts) == 1
        )  # Empty content doesn't add parts, only "Actual response" does
        assert contents[1].parts[0].text == "Actual response"
        assert contents[2].role == "user"
        assert contents[2].parts[0].text == "Thanks"

    def test_consecutive_user_messages(self):
        """Test that consecutive UserPromptMessage inputs are properly merged"""
        messages = [
            UserPromptMessage(content="First question"),
            UserPromptMessage(content="Second question"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # Two consecutive user messages should be merged into one content
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "First question"
        assert contents[0].parts[1].text == "Second question"

        # Test with more consecutive user messages
        messages = [
            UserPromptMessage(content="Question 1"),
            UserPromptMessage(content="Question 2"),
            UserPromptMessage(content="Question 3"),
            UserPromptMessage(content="Question 4"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # All four user messages should be merged into one content
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 4
        assert contents[0].parts[0].text == "Question 1"
        assert contents[0].parts[1].text == "Question 2"
        assert contents[0].parts[2].text == "Question 3"
        assert contents[0].parts[3].text == "Question 4"

        # Test with mixed content types in consecutive user messages
        messages = [
            UserPromptMessage(content="Text message"),
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="Another text"),
                    TextPromptMessageContent(data="And more text"),
                ]
            ),
            UserPromptMessage(content="Final message"),
        ]

        contents = self.llm._build_gemini_contents(
            prompt_messages=messages, genai_client=self.mock_client, config=self.mock_config
        )

        # All user messages should be merged into one content with all parts
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 4
        assert contents[0].parts[0].text == "Text message"
        assert contents[0].parts[1].text == "Another text"
        assert contents[0].parts[2].text == "And more text"
        assert contents[0].parts[3].text == "Final message"

    def test_multimodal_user_message(self):
        """Test user message with mixed text and image content"""
        from unittest.mock import Mock, patch

        messages = [
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="What's in this image?"),
                    ImagePromptMessageContent(
                        format="jpeg",
                        base64_data="dGVzdCBpbWFnZSBkYXRh",  # "test image data" in base64
                        mime_type="image/jpeg",
                    ),
                ]
            )
        ]

        # Mock the file upload
        mock_client = Mock()
        mock_file = Mock()
        mock_file.uri = "gs://test-bucket/test-image.jpg"
        mock_file.mime_type = "image/jpeg"
        mock_file.state.name = "ACTIVE"
        mock_client.files.upload.return_value = mock_file
        mock_client.files.get.return_value = mock_file

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):
            contents = self.llm._build_gemini_contents(
                prompt_messages=messages, genai_client=mock_client, config=self.mock_config
            )

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "What's in this image?"
        assert contents[0].parts[1].file_data.file_uri == "gs://test-bucket/test-image.jpg"
        assert contents[0].parts[1].file_data.mime_type == "image/jpeg"

    def test_file_url_prefix_handling(self):
        """Test handling of file_server_url_prefix parameter"""
        from unittest.mock import Mock, patch

        messages = [
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="Check this document"),
                    DocumentPromptMessageContent(
                        format="pdf", url="/files/document.pdf", mime_type="application/pdf"
                    ),
                ]
            )
        ]

        # Mock the file upload and HTTP request
        mock_client = Mock()
        mock_file = Mock()
        mock_file.uri = "gs://test-bucket/document.pdf"
        mock_file.mime_type = "application/pdf"
        mock_file.state.name = "ACTIVE"
        mock_client.files.upload.return_value = mock_file
        mock_client.files.get.return_value = mock_file

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"), patch(
            "requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.content = b"PDF content"
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            contents = self.llm._build_gemini_contents(
                prompt_messages=messages,
                genai_client=mock_client,
                config=self.mock_config,
                file_server_url_prefix="https://example.com/api",
            )

        # Verify the URL was constructed correctly
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert called_url == "https://example.com/api/files/document.pdf"

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "Check this document"
        assert contents[0].parts[1].file_data.file_uri == "gs://test-bucket/document.pdf"
