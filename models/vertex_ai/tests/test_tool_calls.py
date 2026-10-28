import pytest
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import AssistantPromptMessage, ToolPromptMessage
from google.genai import types

from models.llm.llm import VertexAiLargeLanguageModel, _decode_tool_call_id


@pytest.mark.parametrize("stream", [False, True])
def test_parallel_same_function_calls_keep_distinct_ids_and_signatures(stream):
    llm = VertexAiLargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    parts = [
        types.Part(
            function_call=types.FunctionCall(name="weather", args={"city": city}),
            thought_signature=b"same signature",
        )
        for city in ("Paris", "Tokyo")
    ]
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(parts=parts), finish_reason="STOP")
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=3
        ),
    )
    if stream:
        chunks = list(
            llm._handle_generate_stream_response(
                "gemini-2.5-flash", {}, iter([response]), [], "", object()
            )
        )
        calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
    else:
        calls = llm._handle_generate_response(
            "gemini-2.5-flash", {}, response, []
        ).message.tool_calls

    assert len(calls) == len({call.id for call in calls}) == 2
    replay = llm._format_message_to_genai_content(
        AssistantPromptMessage(content="", tool_calls=calls)
    )
    replay_parts = [types.Part.model_validate(part) for part in replay["parts"]]
    assert [part.function_call.args for part in replay_parts] == [
        {"city": "Paris"},
        {"city": "Tokyo"},
    ]
    assert all(part.thought_signature == b"same signature" for part in replay_parts)
    assert [part.function_call.id for part in replay_parts] == [
        _decode_tool_call_id(call.id)[0] for call in calls
    ]
    tool = llm._format_message_to_genai_content(
        ToolPromptMessage(content="sunny", name="weather", tool_call_id=calls[0].id)
    )
    assert (
        tool["parts"][0]["function_response"]["id"] == replay_parts[0].function_call.id
    )


def test_preserves_provider_call_id():
    llm = VertexAiLargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="provider-call", name="weather", args={}
                            )
                        )
                    ]
                )
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=1, candidates_token_count=1
        ),
    )
    result = llm._handle_generate_response("gemini-2.5-flash", {}, response, [])
    assert result.message.tool_calls[0].id == "provider-call"


@pytest.mark.parametrize("candidates", [None, [types.Candidate(finish_reason="STOP")]])
def test_stream_preserves_usage_without_content(candidates):
    llm = VertexAiLargeLanguageModel([])
    llm._calc_response_usage = lambda model, credentials, prompt, completion: (
        LLMUsage.empty_usage().model_copy(
            update={
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            }
        )
    )
    response = types.GenerateContentResponse(
        candidates=candidates,
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=3
        ),
    )
    chunks = list(
        llm._handle_generate_stream_response(
            "gemini-2.5-flash", {}, iter([response]), [], "", object()
        )
    )
    assert len(chunks) == 1
    assert chunks[0].delta.usage.total_tokens == 13
    assert chunks[0].delta.message.tool_calls == []
