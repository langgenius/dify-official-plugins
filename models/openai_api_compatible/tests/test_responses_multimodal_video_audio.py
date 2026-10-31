"""Video and audio attachments must not be silently dropped on the Responses path.

The Responses API conversion only handled TEXT/IMAGE/DOCUMENT content parts,
so a video or audio attachment disappeared without a trace even though the
credential advertised `video_support`/`audio_support`. The Chat Completions
path already carried these modalities, so the two paths disagreed.
"""

from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)

from models.llm.llm import OpenAILargeLanguageModel


def _video_content() -> VideoPromptMessageContent:
    return VideoPromptMessageContent(
        type="video", format="mp4", base64_data="AAAA", mime_type="video/mp4"
    )


def _audio_content() -> AudioPromptMessageContent:
    return AudioPromptMessageContent(
        type="audio", format="wav", base64_data="BBBB", mime_type="audio/wav"
    )


def test_video_content_is_not_dropped_on_responses_path():
    model = OpenAILargeLanguageModel(model_schemas=[])
    message = UserPromptMessage(content=[_video_content()])

    parts = model._convert_multimodal_content_to_responses_parts(message.content)

    assert len(parts) == 1
    assert parts[0]["type"] == "input_image"
    assert parts[0]["image_url"] == "data:video/mp4;base64,AAAA"


def test_audio_content_is_not_dropped_on_responses_path():
    model = OpenAILargeLanguageModel(model_schemas=[])
    message = UserPromptMessage(content=[_audio_content()])

    parts = model._convert_multimodal_content_to_responses_parts(message.content)

    assert len(parts) == 1
    assert parts[0]["type"] == "input_file"
    assert parts[0]["file_data"] == "data:audio/wav;base64,BBBB"


def test_video_and_audio_preserved_alongside_other_modalities():
    model = OpenAILargeLanguageModel(model_schemas=[])
    message = UserPromptMessage(content=[_video_content(), _audio_content()])

    parts = model._convert_multimodal_content_to_responses_parts(message.content)

    assert len(parts) == 2
    assert parts[0]["type"] == "input_image"
    assert parts[1]["type"] == "input_file"


def test_video_with_url_uses_url_instead_of_data_uri():
    model = OpenAILargeLanguageModel(model_schemas=[])
    video = VideoPromptMessageContent(
        type="video",
        format="mp4",
        url="https://example.com/clip.mp4",
        mime_type="video/mp4",
    )
    message = UserPromptMessage(content=[video])

    parts = model._convert_multimodal_content_to_responses_parts(message.content)

    assert len(parts) == 1
    assert parts[0]["image_url"] == "https://example.com/clip.mp4"
