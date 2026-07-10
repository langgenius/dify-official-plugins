from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from dify_plugin.errors.model import InvokeBadRequestError
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageTool,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)

pytestmark = pytest.mark.live

_USER = "dify-openai-live-test"
_RED_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKElEQVR4nO3NsQ0A"
    "AAzCMP5/un0CNkuZ41wybXsHAAAAAAAAAAAAxR4yw/wuPL6QkAAAAABJRU5ErkJggg=="
)
_AUDIO_FILE = Path(__file__).resolve().parents[2] / "_assets" / "audio.mp3"


def _parameters(llm, model: str, max_tokens: int = 32) -> dict:
    parameters = {"max_tokens": max_tokens}
    schema = llm.get_model_schema(model, {})
    rules = {rule.name: rule for rule in schema.parameter_rules}
    if rule := rules.get("reasoning_effort"):
        parameters["reasoning_effort"] = next(
            value
            for value in ("none", "minimal", "low", "medium")
            if value in rule.options
        )
    if rule := rules.get("verbosity"):
        if "low" in rule.options:
            parameters["verbosity"] = "low"
    return parameters


def _invoke(
    llm,
    credentials: dict,
    model: str,
    messages: list,
    *,
    parameters: dict | None = None,
    tools: list[PromptMessageTool] | None = None,
    stop: list[str] | None = None,
    stream: bool = True,
):
    try:
        return list(
            llm.invoke(
                model=model,
                credentials=credentials,
                prompt_messages=messages,
                model_parameters=parameters or _parameters(llm, model),
                tools=tools,
                stop=stop,
                stream=stream,
                user=_USER,
            )
        )
    except InvokeBadRequestError as error:
        if "organization must be verified" in str(error).lower():
            pytest.skip("OpenAI requires organization verification for this model")
        raise


def _terminal(chunks):
    assert chunks
    terminal = chunks[-1].delta
    assert terminal.usage is not None
    assert terminal.usage.total_tokens > 0
    return terminal


def _text(chunks) -> str:
    return "".join(
        chunk.delta.message.content
        for chunk in chunks
        if isinstance(chunk.delta.message.content, str)
    )


def _audio_message(prompt: str) -> UserPromptMessage:
    return UserPromptMessage(
        content=[
            TextPromptMessageContent(data=prompt),
            AudioPromptMessageContent(
                base64_data=base64.b64encode(_AUDIO_FILE.read_bytes()).decode(),
                format="mp3",
                mime_type="audio/mpeg",
                filename="speech.mp3",
            ),
        ]
    )


def test_every_presented_llm_accepts_a_minimal_request(
    live_llm, live_credentials, llm_model
):
    schema = live_llm.get_model_schema(llm_model, live_credentials)
    message = (
        _audio_message("Does this audio contain speech? Reply briefly.")
        if ModelFeature.AUDIO in (schema.features or [])
        else UserPromptMessage(content="Reply with OK.")
    )
    chunks = _invoke(
        live_llm,
        live_credentials,
        llm_model,
        [message],
        stream=ModelFeature.STREAM_TOOL_CALL in (schema.features or []),
    )

    _terminal(chunks)


@pytest.mark.parametrize("stream", [False, True], ids=["nonstream", "stream"])
def test_chat_completions_protocol(
    live_llm, live_credentials, require_live_model, stream
):
    model = require_live_model("gpt-4o-mini")
    credentials = type(live_credentials)(
        live_credentials,
        api_protocol="chat",
    )
    chunks = _invoke(
        live_llm,
        credentials,
        model,
        [UserPromptMessage(content="Reply with OK.")],
        parameters={"max_tokens": 16, "temperature": 0},
        stream=stream,
    )

    assert _text(chunks).strip()
    _terminal(chunks)


@pytest.mark.parametrize("stream", [False, True], ids=["nonstream", "stream"])
@pytest.mark.parametrize("protocol", ["responses", "chat"])
def test_structured_output_matches_schema(
    live_llm, live_credentials, require_live_model, protocol, stream
):
    model = require_live_model("gpt-4o-mini")
    credentials = type(live_credentials)(
        live_credentials,
        api_protocol=protocol,
    )
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": ["ok"]}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    chunks = _invoke(
        live_llm,
        credentials,
        model,
        [UserPromptMessage(content="Return the required structured answer.")],
        parameters={
            "max_tokens": 32,
            "response_format": "json_schema",
            "json_schema": json.dumps(schema),
        },
        stream=stream,
    )

    assert json.loads(_text(chunks)) == {"answer": "ok"}
    _terminal(chunks)


def test_reasoning_summary_is_separate_and_preserved(
    live_llm, live_credentials, require_live_model
):
    model = require_live_model("gpt-5.6")
    chunks = _invoke(
        live_llm,
        live_credentials,
        model,
        [UserPromptMessage(content="Calculate 17 multiplied by 19.")],
        parameters={
            "max_tokens": 256,
            "reasoning_effort": "low",
            "reasoning_summary": "auto",
            "verbosity": "low",
        },
    )

    content = _text(chunks)
    if "<think>" not in content:
        pytest.skip(
            "OpenAI did not return a reasoning summary; organization "
            "verification may be required"
        )
    terminal = _terminal(chunks)
    output = terminal.message.opaque_body["responses_output"]
    assert any(item["type"] == "reasoning" for item in output)
    assert any(item["type"] == "message" for item in output)
    assert content.count("<think>") == content.count("</think>") == 1
    assert content.split("</think>", 1)[1].strip()


def test_tool_stream_and_replay_reasoning(
    live_llm, live_credentials, require_live_model
):
    model = require_live_model("gpt-5-nano")
    tools = [
        PromptMessageTool(
            name="lookup_city",
            description="Look up a city",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            },
        )
    ]
    prompt = UserPromptMessage(
        content=(
            "Call lookup_city exactly once for Paris. Use its result before answering."
        )
    )
    first = _invoke(
        live_llm,
        live_credentials,
        model,
        [prompt],
        parameters={
            "max_tokens": 128,
            "reasoning_effort": "minimal",
            "verbosity": "low",
        },
        tools=tools,
    )
    assistant = _terminal(first).message

    assert len(assistant.tool_calls) == 1
    call = assistant.tool_calls[0]
    assert call.function.name == "lookup_city"
    assert json.loads(call.function.arguments)["city"].lower() == "paris"
    output = assistant.opaque_body["responses_output"]
    reasoning = next(item for item in output if item["type"] == "reasoning")
    assert reasoning["encrypted_content"]

    second = _invoke(
        live_llm,
        live_credentials,
        model,
        [
            prompt,
            assistant,
            ToolPromptMessage(
                content='{"country": "France"}',
                tool_call_id=call.id,
            ),
        ],
        parameters={
            "max_tokens": 128,
            "reasoning_effort": "minimal",
            "verbosity": "low",
        },
        tools=tools,
    )

    terminal = _terminal(second)
    assert _text(second).strip()
    assert terminal.finish_reason == "stop"
    assert terminal.message.tool_calls == []


def test_image_input(live_llm, live_credentials, require_live_model):
    model = require_live_model("gpt-4o-mini")
    message = UserPromptMessage(
        content=[
            TextPromptMessageContent(
                data=(
                    "What single primary color fills this image? "
                    "Reply only with the color name."
                )
            ),
            ImagePromptMessageContent(
                base64_data=_RED_IMAGE,
                format="png",
                mime_type="image/png",
                filename="pixel.png",
            ),
        ]
    )

    chunks = _invoke(live_llm, live_credentials, model, [message])

    assert _text(chunks).strip(" .!`\"'").upper() == "RED"
    _terminal(chunks)


def test_document_input(live_llm, live_credentials, require_live_model):
    model = require_live_model("gpt-4o-mini")
    document = base64.b64encode(b"The live document marker is ORCHID.").decode()
    message = UserPromptMessage(
        content=[
            DocumentPromptMessageContent(
                base64_data=document,
                format="txt",
                mime_type="text/plain",
                filename="marker.txt",
            ),
            TextPromptMessageContent(data="Return only the marker from the document."),
        ]
    )

    chunks = _invoke(live_llm, live_credentials, model, [message])

    assert "ORCHID" in _text(chunks).upper()
    _terminal(chunks)


def test_audio_input(live_llm, live_credentials, require_live_model):
    model = require_live_model("gpt-audio-1.5")
    message = _audio_message(
        "Does this audio contain spoken human speech? Reply only SPEECH or SILENCE."
    )

    chunks = _invoke(
        live_llm,
        live_credentials,
        model,
        [message],
        parameters={"max_tokens": 32, "temperature": 0},
        stream=False,
    )

    assert _text(chunks).strip(" .!`\"'").upper() == "SPEECH"
    _terminal(chunks)


def test_streaming_stop_sequence(live_llm, live_credentials, require_live_model):
    model = require_live_model("gpt-4o-mini")
    chunks = _invoke(
        live_llm,
        live_credentials,
        model,
        [
            UserPromptMessage(
                content="Write exactly alpha<END>omega, with no spaces or punctuation."
            )
        ],
        parameters={"max_tokens": 32, "temperature": 0},
        stop=["<END>"],
    )

    content = _text(chunks)
    terminal = _terminal(chunks)
    assert "alpha" in content.lower()
    assert "<END>" not in content
    assert "omega" not in content.lower()
    assert terminal.finish_reason == "stop"
    assert terminal.message.opaque_body is None


def test_incomplete_response_reports_length(
    live_llm, live_credentials, require_live_model
):
    model = require_live_model("gpt-5-nano")
    chunks = _invoke(
        live_llm,
        live_credentials,
        model,
        [UserPromptMessage(content="Write a detailed explanation of photosynthesis.")],
        parameters={"max_tokens": 16, "reasoning_effort": "minimal"},
    )

    assert _terminal(chunks).finish_reason == "length"
