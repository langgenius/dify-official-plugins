from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import AssistantPromptMessage

from models.llm.llm import OpenAILargeLanguageModel


def _chunk(index: int, content: str, finish_reason: str | None = None) -> LLMResultChunk:
    return LLMResultChunk(
        model="test-model",
        delta=LLMResultChunkDelta(
            index=index,
            message=AssistantPromptMessage(content=content),
            finish_reason=finish_reason,
        ),
    )


def _filter(*contents: str) -> list[LLMResultChunk]:
    model = OpenAILargeLanguageModel(model_schemas=[])
    chunks = (_chunk(index, content) for index, content in enumerate(contents))
    return list(model._filter_thinking_stream(chunks))


def _filtered_text(*contents: str) -> str:
    return "".join(chunk.delta.message.content for chunk in _filter(*contents))


def test_filter_thinking_stream_removes_think_tag_in_single_chunk():
    assert _filtered_text("<think>", "reasoning", "</think>", "\n\nanswer") == "answer"


def test_filter_thinking_stream_removes_think_tag_split_across_chunks():
    assert _filtered_text("<", "think", ">", "reasoning", "</think>", "\n\nanswer") == "answer"


def test_filter_thinking_stream_removes_think_tag_split_mid_tag():
    assert _filtered_text("<th", "ink>reasoning</th", "ink>answer") == "answer"


def test_filter_thinking_stream_skips_whitespace_chunks_after_think_tag():
    assert _filtered_text("<think>reasoning</think>", "\n", "\n", "answer") == "answer"


def test_filter_thinking_stream_keeps_whitespace_inside_answer():
    assert _filtered_text("<think>reasoning</think>answer", " ", "text") == "answer text"


def test_filter_thinking_stream_removes_consecutive_think_blocks():
    assert _filtered_text("<think>a</think>", "<think>b</think>", "answer") == "answer"


def test_filter_thinking_stream_keeps_content_starting_like_think_tag():
    assert _filtered_text("<", "b>bold</b>") == "<b>bold</b>"


def test_filter_thinking_stream_flushes_partial_tag_at_end_of_stream():
    assert _filtered_text("answer ", "<th") == "answer <th"


def test_filter_thinking_stream_flushes_partial_tag_before_final_chunk():
    model = OpenAILargeLanguageModel(model_schemas=[])
    chunks = [_chunk(0, "answer "), _chunk(1, "<"), _chunk(2, "", finish_reason="stop")]

    result = list(model._filter_thinking_stream(iter(chunks)))

    assert [(c.delta.message.content, c.delta.finish_reason) for c in result] == [
        ("answer ", None),
        ("<", None),
        ("", "stop"),
    ]


def test_filter_thinking_stream_keeps_content_without_think_tag():
    assert _filtered_text("plain", " answer") == "plain answer"


def test_filter_thinking_stream_drops_unclosed_split_think_tag():
    assert _filtered_text("<", "think>", "reasoning") == ""
