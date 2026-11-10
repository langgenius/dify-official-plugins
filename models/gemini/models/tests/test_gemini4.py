import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    UserPromptMessage,
)
from google import genai
from google.genai import types
from google.genai.models import Models
from models.llm.llm import GoogleLargeLanguageModel


MODEL = "gemini-4-argon"


@pytest.fixture
def llm():
    schema_path = Path(__file__).parents[1] / "llm" / f"{MODEL}.yaml"
    return GoogleLargeLanguageModel(
        [AIModelEntity(**yaml.safe_load(schema_path.read_text()))]
    )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "tool", ["grounding", "url_context", "code_execution", "function"]
)
def test_structured_output_with_tools_uses_generate_content(llm, stream, tool):
    client = Mock()
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    parameters = {
        "json_schema": json.dumps(schema),
        "max_output_tokens": 131_072,
        "thinking_level": "High",
        "service_tier": "flex",
        "media_resolution": "High",
        "include_thoughts": True,
    }
    tools = None
    if tool == "function":
        tools = [
            PromptMessageTool(name="lookup", description="Look up facts", parameters={})
        ]
    else:
        parameters[tool] = True

    with (
        patch("models.llm.llm.genai.Client", return_value=client) as constructor,
        patch.object(llm, "_handle_generate_response"),
        patch.object(llm, "_handle_generate_stream_response"),
    ):
        llm._generate(
            model=MODEL,
            credentials={
                "google_api_key": "test-key",
                "google_base_url": "https://example.com",
            },
            prompt_messages=[
                UserPromptMessage(content="Research this and return JSON.")
            ],
            model_parameters=parameters,
            tools=tools,
            stream=stream,
        )

    request = (
        client.models.generate_content_stream
        if stream
        else client.models.generate_content
    ).call_args.kwargs
    config = request["config"]
    assert request["model"] == MODEL
    assert config.response_json_schema == schema
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 131_072
    assert config.thinking_config.thinking_level == types.ThinkingLevel.HIGH
    assert config.thinking_config.include_thoughts is True
    assert config.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_HIGH
    assert config.service_tier == types.ServiceTier.FLEX
    tool_field = {
        "grounding": "google_search",
        "function": "function_declarations",
    }.get(tool, tool)
    assert getattr(config.tools[0], tool_field) is not None
    http_options = constructor.call_args.kwargs["http_options"]
    assert http_options.timeout == 900_000
    assert http_options.base_url == "https://example.com"
    client.interactions.create.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
def test_sdk_continuation_preserves_text_and_billed_usage(llm, stream):
    first = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text="First ")]),
                finish_reason=types.FinishReason.CONTINUATION,
                continuation_token=b"next-hop",
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10,
            candidates_token_count=2,
            thoughts_token_count=5,
        ),
    )
    last = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text="second")]),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=11,
            candidates_token_count=3,
            thoughts_token_count=7,
        ),
    )
    if stream:
        text_chunk = types.GenerateContentResponse(
            candidates=[types.Candidate(content=last.candidates[0].content)]
        )
        last.candidates[0].content = None
        responses = [iter([first]), iter([text_chunk, last])]
    else:
        responses = [first, last]

    method = "_generate_content_stream" if stream else "_generate_content"
    with (
        genai.Client(
            api_key="test-key",
            http_options=types.HttpOptions(
                client_args={"trust_env": False},
                async_client_args={"trust_env": False},
            ),
        ) as client,
        patch("models.llm.llm.genai.Client", return_value=client),
        patch.object(Models, method, side_effect=responses) as transport,
        patch.object(llm, "get_num_tokens") as estimate_tokens,
    ):
        chunks = list(
            llm.invoke(
                model=MODEL,
                credentials={"google_api_key": "test-key"},
                prompt_messages=[UserPromptMessage(content="Solve this.")],
                model_parameters={"max_output_tokens": 131_072},
                stream=stream,
            )
        )

    assert (
        "".join(part.data for chunk in chunks for part in chunk.delta.message.content)
        == "First second"
    )
    assert transport.call_count == 2
    calls = transport.call_args_list
    assert calls[1].kwargs["contents"] == calls[0].kwargs["contents"]
    assert calls[1].kwargs["config"].continuation_token == b"next-hop"
    assert calls[1].kwargs["config"].max_output_tokens == 131_072
    usages = [chunk.delta.usage for chunk in chunks if chunk.delta.usage is not None]
    assert len(usages) == 1
    assert usages[0].prompt_tokens == 21
    assert usages[0].completion_tokens == 17
    assert usages[0].total_price == Decimal("0.000212")
    assert all(
        chunk.delta.finish_reason != types.FinishReason.CONTINUATION for chunk in chunks
    )
    estimate_tokens.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
def test_zero_output_usage_is_not_replaced_by_an_estimate(llm, stream):
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(finish_reason=types.FinishReason.STOP)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10,
            candidates_token_count=0,
            thoughts_token_count=0,
        ),
    )
    with llm.timing_context(), patch.object(llm, "get_num_tokens") as estimate_tokens:
        if stream:
            chunks = list(
                llm._handle_generate_stream_response(
                    MODEL, {}, iter([response]), [], Mock()
                )
            )
            usage = chunks[-1].delta.usage
        else:
            usage = llm._handle_generate_response(MODEL, {}, response, []).usage
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 0
    estimate_tokens.assert_not_called()


@pytest.mark.parametrize("thought", [False, True])
@pytest.mark.parametrize("ending", [None, [], [types.Part(text="Done.")]])
def test_stream_usage_fallback_counts_all_output(llm, thought, ending):
    fragments = ["The quick brown fox jumps ", "over the lazy dog. " * 100]
    prompt_messages = [UserPromptMessage(content="Tell me a story.")]
    responses = [
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(text=text, thought=True if thought else None)
                        ],
                    )
                )
            ]
        )
        for text in fragments
    ]
    responses.append(
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(role="model", parts=ending)
                    if ending is not None
                    else None,
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        )
    )
    with llm.timing_context():
        chunks = list(
            llm._handle_generate_stream_response(
                MODEL, {}, iter(responses), prompt_messages, Mock()
            )
        )

    text = "".join(fragments)
    terminal_text = "Done." if ending else ""
    if thought:
        text = f"<think>\n\n{text}"
        terminal_text = f"\n\n</think>{terminal_text}"
    expected = text + terminal_text
    assert len(chunks) == 3
    assert "".join(p.data for c in chunks for p in c.delta.message.content) == expected
    assert "".join(p.data for p in chunks[-1].delta.message.content) == terminal_text
    assert all(c.delta.usage is None for c in chunks[:-1])
    assert chunks[-1].delta.finish_reason == types.FinishReason.STOP
    assert chunks[-1].delta.usage.completion_tokens == llm.get_num_tokens(
        MODEL, {}, [AssistantPromptMessage(content=expected)]
    )
    assert chunks[-1].delta.usage.prompt_tokens == llm.get_num_tokens(
        MODEL, {}, prompt_messages
    )


@pytest.mark.parametrize("stream", [False, True])
def test_usage_fallback_counts_tool_names_and_arguments(llm, stream):
    calls = [
        types.FunctionCall(
            id="weather-1", name="lookup_weather", args={"city": "London"}
        ),
        types.FunctionCall(
            id="weather-2", name="lookup_forecast", args={"city": "Paris", "days": 7}
        ),
    ]
    parts = [types.Part(function_call=call) for call in calls]
    with (
        llm.timing_context(),
        patch.object(
            llm, "_get_num_tokens_by_gpt2", wraps=llm._get_num_tokens_by_gpt2
        ) as tokenize,
    ):
        if stream:
            responses = [
                types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            content=types.Content(role="model", parts=[part])
                        )
                    ]
                )
                for part in parts
            ]
            responses.append(
                types.GenerateContentResponse(
                    candidates=[types.Candidate(finish_reason=types.FinishReason.STOP)]
                )
            )
            chunks = list(
                llm._handle_generate_stream_response(
                    MODEL, {}, iter(responses), [], Mock()
                )
            )
            messages = [c.delta.message for c in chunks]
            usage = chunks[-1].delta.usage
            assert chunks[-1].delta.message.tool_calls == []
        else:
            response = types.GenerateContentResponse(
                candidates=[
                    types.Candidate(content=types.Content(role="model", parts=parts))
                ]
            )
            result = llm._handle_generate_response(MODEL, {}, response, [])
            messages, usage = [result.message], result.usage

    tokenized_output = tokenize.call_args.args[0]
    for call in calls:
        assert call.name in tokenized_output
        assert json.dumps(call.args) in tokenized_output
    assert [call.id for message in messages for call in message.tool_calls] == [
        "weather-1",
        "weather-2",
    ]
    assert usage.completion_tokens == llm._get_num_tokens_by_gpt2(tokenized_output)
