import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from dify_plugin.core.runtime import Session
from dify_plugin.core.server.stdio.request_reader import StdioRequestReader
from dify_plugin.core.server.stdio.response_writer import StdioResponseWriter
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
    ensure_prompt_message,
)
from models.llm import responses
from models.llm import stream as response_stream
from openai import OpenAI
from openai.types.responses import Response


@pytest.mark.parametrize("stream", [False, True])
def test_sdk_tool_round_trip_preserves_responses_output(stream, llm, monkeypatch):
    output = [
        {
            "id": "rs_1",
            "type": "reasoning",
            "status": "completed",
            "encrypted_content": "ciphertext",
            "summary": [{"type": "summary_text", "text": "Plan"}],
        },
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "phase": "commentary",
            "content": [{"type": "output_text", "text": "Checking", "annotations": []}],
        },
        {
            "id": "fc_1",
            "type": "function_call",
            "call_id": "call_1",
            "name": "tool_1",
            "arguments": "{}",
            "status": "completed",
        },
    ]
    terminal = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-6-sol",
        "status": "completed",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }
    requests = []

    def provider_response(request):
        requests.append(json.loads(request.content))
        if stream:
            event = {
                "type": "response.completed",
                "sequence_number": 0,
                "response": terminal,
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"event: response.completed\ndata: {json.dumps(event)}\n\n",
            )
        return httpx.Response(200, json=terminal)

    client_type = httpx.Client
    client = OpenAI(
        api_key="test",
        http_client=client_type(transport=httpx.MockTransport(provider_response)),
    )

    def host_response(request):
        invocation = json.loads(request.content)["data"]["data"]
        messages = [
            ensure_prompt_message(value)
            for value in invocation["request"]["prompt_messages"]
        ]
        generate = response_stream.generate if stream else responses.generate
        result = generate(llm, client, "gpt-6-sol", {}, messages, {}, None, None, None)
        chunks = (
            list(result)
            if stream
            else [
                LLMResultChunk(
                    model=result.model,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=result.message,
                        usage=result.usage,
                    ),
                )
            ]
        )
        chunks.append(
            LLMResultChunk(
                model="gpt-6-sol",
                delta=LLMResultChunkDelta(
                    index=len(chunks),
                    message=AssistantPromptMessage(content=""),
                ),
            )
        )
        events = [
            {
                "session_id": "replay",
                "event": "backwards_response",
                "data": {
                    "backwards_request_id": invocation["backwards_request_id"],
                    "event": "response",
                    "message": "",
                    "data": chunk.model_dump(mode="json"),
                },
            }
            for chunk in chunks
        ]
        return httpx.Response(200, text="\n".join(map(json.dumps, events)))

    monkeypatch.setattr(
        "dify_plugin.core.runtime.httpx",
        SimpleNamespace(
            Client=lambda: client_type(transport=httpx.MockTransport(host_response)),
        ),
    )
    with client, ThreadPoolExecutor(max_workers=1) as executor:
        session = Session(
            session_id="replay",
            executor=executor,
            reader=StdioRequestReader(),
            writer=StdioResponseWriter(),
            dify_plugin_daemon_url="http://daemon.test",
        )
        history = [UserPromptMessage(content="Use tool_1")]
        config = {"provider": "openai", "model": "gpt-6-sol", "mode": "chat"}
        result = session.model.llm.invoke(
            model_config=config, prompt_messages=history, stream=stream
        )
        if stream:
            chunks = list(result)
            assistant = AssistantPromptMessage(
                content="".join(
                    chunk.delta.message.get_text_content() for chunk in chunks
                ),
                tool_calls=[
                    call for chunk in chunks for call in chunk.delta.message.tool_calls
                ],
                opaque_body=next(
                    chunk.delta.message.opaque_body
                    for chunk in reversed(chunks)
                    if chunk.delta.message.opaque_body is not None
                ),
            )
        else:
            assistant = result.message
        history.extend(
            [assistant, ToolPromptMessage(tool_call_id="call_1", content="found")]
        )
        result = session.model.llm.invoke(
            model_config=config, prompt_messages=history, stream=stream
        )
        if stream:
            list(result)
    assert len(requests) == 2
    replay = requests[1]["input"]
    expected = Response.model_validate(terminal).model_dump(
        mode="json", exclude_none=True
    )["output"]
    assert replay[1:-1] == expected
    assert replay[-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "found",
    }
