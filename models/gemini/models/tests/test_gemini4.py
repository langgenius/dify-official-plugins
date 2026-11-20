import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
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
@pytest.mark.parametrize(
    ("model", "level"),
    [
        ("gemini-4-argon", "High"),
        ("gemini-4-carbon", "High"),
        ("gemini-4-hydrogen", "Xhigh"),
        ("gemini-4-neon", "Xhigh"),
    ],
)
def test_structured_output_with_tools_uses_generate_content(
    llm, stream, tool, model, level
):
    client = Mock()
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    parameters = {
        "json_schema": json.dumps(schema),
        "max_output_tokens": 131_072,
        "thinking_level": level,
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
            model=model,
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
    assert request["model"] == model
    assert config.response_json_schema == schema
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 131_072
    if level == "Xhigh":
        assert (
            config.http_options.extra_body["generationConfig"]["thinkingConfig"][
                "thinkingLevel"
            ]
            == "XHIGH"
        )
    else:
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
@pytest.mark.parametrize(
    ("model", "price"),
    [
        ("gemini-4-argon", "0.000212"),
        ("gemini-4-carbon", "0.000212"),
        ("gemini-4-hydrogen", "0.000159"),
        ("gemini-4-neon", "0.000318"),
    ],
)
def test_sdk_continuation_preserves_text_and_billed_usage(stream, model, price):
    path = Path(__file__).parents[1] / "llm" / f"{model}.yaml"
    llm = GoogleLargeLanguageModel([AIModelEntity(**yaml.safe_load(path.read_text()))])
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
        patch("models.llm.llm.datetime") as clock,
        patch.object(llm, "get_num_tokens") as estimate_tokens,
    ):
        clock.now.return_value = datetime(2026, 11, 30)
        chunks = list(
            llm.invoke(
                model=model,
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
    assert usages[0].total_price == Decimal(price)
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


@pytest.mark.parametrize("stream", [False, True])
def test_signed_parallel_tools_round_trip(stream):
    model = "gemini-4-neon"
    llm = GoogleLargeLanguageModel([])
    parts = [
        types.Part(
            function_call=types.FunctionCall(name="first", args={}),
            thought_signature=b"\xffsignature",
        ),
        types.Part(
            function_call=types.FunctionCall(id="second-id", name="second", args={})
        ),
    ]
    reply = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts), finish_reason="STOP"
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=1),
    )
    with llm.timing_context():
        if stream:
            first = types.GenerateContentResponse(
                candidates=[types.Candidate(content=reply.candidates[0].content)]
            )
            reply.candidates[0].content = None
            chunks = list(
                llm._handle_generate_stream_response(
                    model, {}, iter([first, reply]), [], Mock()
                )
            )
            assistant = chunks[0].delta.message
            assistant.opaque_body = chunks[-1].delta.message.opaque_body
        else:
            assistant = llm._handle_generate_response(model, {}, reply, []).message
    messages = [UserPromptMessage(content="Use both tools"), assistant]
    for call in assistant.tool_calls:
        messages.append(
            ToolPromptMessage(
                name=call.function.name, tool_call_id=call.id, content="ok"
            )
        )
    history = llm._build_gemini_contents(
        messages, Mock(), types.GenerateContentConfig()
    )
    assert history[1].parts == parts
    assert [part.function_response.id for part in history[2].parts] == [
        None,
        "second-id",
    ]


def test_xhigh_sdk_serializes_native_field():
    import httpx

    captured = []

    def transport(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ]
            },
        )

    with genai.Client(
        api_key="test",
        http_options=types.HttpOptions(
            client_args={
                "transport": httpx.MockTransport(transport),
                "trust_env": False,
            },
            async_client_args={"trust_env": False},
        ),
    ) as client:
        config = types.GenerateContentConfig()
        GoogleLargeLanguageModel._set_thinking_config(
            config=config,
            model_parameters={"thinking_level": "Xhigh", "include_thoughts": True},
            model_name="gemini-4-neon",
        )
        client.models.generate_content(
            model="gemini-4-neon", contents="Hi", config=config
        )
    assert captured[0]["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "XHIGH",
        "include_thoughts": True,
    }


def test_nano_banana_image_configuration_and_mixed_output_pricing():
    model = "gemini-nano-banana-2.1"
    path = Path(__file__).parents[1] / "llm" / f"{model}.yaml"
    llm = GoogleLargeLanguageModel([AIModelEntity(**yaml.safe_load(path.read_text()))])
    config = types.GenerateContentConfig()
    llm._set_image_config(
        config=config,
        model_parameters={"aspect_ratio": "8:1", "resolution": "4K"},
        model=model,
    )
    llm._set_thinking_config(
        config=config, model_parameters={"thinking_level": "Medium"}, model_name=model
    )
    llm._set_response_modalities(config=config, model_name=model)
    assert config.http_options.api_version == "v1"
    assert (config.image_config.aspect_ratio, config.image_config.image_size) == (
        "8:1",
        "4K",
    )
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM
    assert config.response_modalities == ["TEXT", "IMAGE"]

    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text="Done")])
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10,
            candidates_token_count=102,
            thoughts_token_count=3,
            candidates_tokens_details=[
                types.ModalityTokenCount(modality="IMAGE", token_count=100)
            ],
        ),
    )
    with llm.timing_context():
        usage = llm._handle_generate_response(model, {}, response, []).usage
    assert usage.completion_tokens == 105
    assert usage.total_price == Decimal("0.0030525")
