import base64

import pytest
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DocumentPromptMessageContent,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError
from protocol_http import PDF, TOOL, chat_result, contents, invoke
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire


@pytest.mark.parametrize("stream", [False, True])
def test_qwen_long_preserves_documents_and_source_message_groups(llm, wire, stream):
    _, requests, replies = wire
    result = chat_result("document answer")
    if stream:
        result["choices"][0]["delta"] = result["choices"][0].pop("message")
        payload = __import__("json").dumps(result)
        replies.append((200, {}, f"data: {payload}\n\ndata: [DONE]\n\n".encode()))
    else:
        replies.append((200, {}, result))
    messages = [
        SystemPromptMessage(content="  Read the documents.  "),
        UserPromptMessage(content=[TextPromptMessageContent(data="  First question  "), PDF]),
        UserPromptMessage(content="  Second question  "),
        AssistantPromptMessage(content=""),
        UserPromptMessage(content="Follow up"),
    ]
    assert contents(invoke(llm, "qwen-long", messages=messages, stream=stream)) == "document answer"
    assert requests[0][0] == "/v1/chat/completions"
    assert requests[0][2]["messages"] == [
        {"role": "system", "content": "Read the documents."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "First question\nSecond question"},
                {
                    "type": "file",
                    "file": {
                        "filename": "sample.pdf",
                        "file_data": f"data:application/pdf;base64,{PDF.base64_data}",
                    },
                },
            ],
        },
        {"role": "assistant", "content": " "},
        {"role": "user", "content": "Follow up"},
    ]
    assert messages[1].content[1] is PDF


@pytest.mark.parametrize(
    "messages,tools",
    [
        ([UserPromptMessage(content=[PDF])], None),
        ([UserPromptMessage(content="question")], [TOOL]),
        ([ToolPromptMessage(content="result", tool_call_id="call")], None),
        ([SystemPromptMessage(content=[PDF]), UserPromptMessage(content="question")], None),
        ([AssistantPromptMessage(content=[PDF]), UserPromptMessage(content="question")], None),
        (
            [
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="question"),
                        DocumentPromptMessageContent(
                            format="pdf", mime_type="application/pdf", base64_data="!invalid!"
                        ),
                    ]
                )
            ],
            None,
        ),
        (
            [
                UserPromptMessage(
                    content=[
                        TextPromptMessageContent(data="question"),
                        DocumentPromptMessageContent(
                            format="pdf",
                            mime_type="application/pdf",
                            url="https://example.invalid/a",
                        ),
                    ]
                )
            ],
            None,
        ),
        (
            [
                UserPromptMessage(
                    content=[TextPromptMessageContent(data="question"), *([PDF] * 101)]
                )
            ],
            None,
        ),
    ],
)
def test_qwen_long_invalid_inputs_make_no_http_request(llm, wire, messages, tools):
    with pytest.raises(InvokeBadRequestError):
        invoke(llm, "qwen-long", messages=messages, tools=tools)
    assert not wire[1]


def test_qwen_long_encoded_and_decoded_limits_are_checked_before_http(llm, wire, monkeypatch):
    from models.llm import _qwen_long

    monkeypatch.setattr(_qwen_long, "DOCUMENT_MAX_BYTES", 4)
    for data in (b"12345", b"1234567"):
        document = DocumentPromptMessageContent(
            format="pdf", mime_type="application/pdf", base64_data=base64.b64encode(data).decode()
        )
        with pytest.raises(InvokeBadRequestError):
            invoke(
                llm,
                "qwen-long",
                messages=[
                    UserPromptMessage(content=[TextPromptMessageContent(data="question"), document])
                ],
            )
    assert not wire[1]
