from __future__ import annotations

from collections.abc import Generator, Iterable
from typing import TYPE_CHECKING, Any, cast

from openai import OpenAI

from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeConnectionError, InvokeServerUnavailableError

from . import responses

if TYPE_CHECKING:
    from .llm import OpenAILargeLanguageModel


def generate(
    llm: OpenAILargeLanguageModel,
    client: OpenAI,
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    model_parameters: dict,
    tools: list[PromptMessageTool] | None,
    stop: list[str] | None,
    user: str | None,
) -> Generator[LLMResultChunk, None, None]:
    events = client.responses.create(
        model=model,
        input=cast(Any, responses.input_items(prompt_messages)),
        stream=True,
        **responses.parameters(model_parameters, tools, user),
    )
    buffer = StopBuffer(stop)
    formatted = ""
    thinking = False
    terminal = None
    incomplete_reason = None
    fragments: dict[int, dict[str, Any]] = {}

    try:
        for event in cast(Iterable[Any], events):
            event_type = responses.field(event, "type", "")
            if event_type == "response.reasoning_summary_text.delta":
                piece = responses.field(event, "delta", "") or ""
                if piece:
                    if not thinking:
                        piece = "<think>\n" + piece
                        thinking = True
                    formatted += piece
                    if visible := buffer.push(piece):
                        yield chunk(model, visible)
            elif event_type in ("response.output_text.delta", "response.refusal.delta"):
                piece = responses.field(event, "delta", "") or ""
                if piece:
                    if thinking:
                        piece = "\n</think>\n" + piece
                        thinking = False
                    formatted += piece
                    if visible := buffer.push(piece):
                        yield chunk(model, visible)
            elif event_type.startswith(
                "response.function_call_arguments."
            ) or event_type in (
                "response.output_item.added",
                "response.output_item.done",
            ):
                track_call(fragments, event)
            elif event_type == "response.completed":
                terminal = responses.field(event, "response")
                responses.raise_for_status(terminal)
                break
            elif event_type == "response.incomplete":
                terminal = responses.field(event, "response")
                responses.raise_for_status(terminal, allow_incomplete=True)
                incomplete_reason = responses.field(
                    responses.field(terminal, "incomplete_details"),
                    "reason",
                )
                break
            elif event_type == "response.failed":
                responses.raise_for_status(responses.field(event, "response"))
                raise InvokeServerUnavailableError("OpenAI response failed")
            elif event_type == "error":
                responses.raise_error(event)
            elif event_type == "response.cancelled":
                raise InvokeServerUnavailableError("OpenAI response was cancelled")
    finally:
        close = getattr(events, "close", None)
        if callable(close):
            close()

    if terminal is None:
        raise InvokeConnectionError(
            "OpenAI Responses stream ended without a terminal event"
        )

    if thinking:
        piece = "\n</think>\n"
        formatted += piece
        if buffer.stopped:
            yield chunk(model, piece)
        elif visible := buffer.push(piece):
            yield chunk(model, visible)

    canonical = responses.content(terminal)
    if not formatted:
        formatted = canonical
        if visible := buffer.push(canonical):
            yield chunk(model, visible)
    elif canonical.startswith(formatted):
        remainder = canonical[len(formatted) :]
        formatted += remainder
        if visible := buffer.push(remainder):
            yield chunk(model, visible)
    if visible := buffer.finish():
        yield chunk(model, visible)

    status = responses.field(terminal, "status")
    calls = (
        responses.response_calls(terminal)
        if status == "completed" and not buffer.stopped
        else []
    )
    if not calls and status == "completed" and not buffer.stopped:
        calls = fragment_calls(fragments)
    finish_reason = {
        "max_output_tokens": "length",
        "content_filter": "content_filter",
    }.get(incomplete_reason, "incomplete" if status == "incomplete" else "stop")
    if calls:
        finish_reason = "tool_calls"
    if buffer.stopped:
        finish_reason = "stop"

    yield LLMResultChunk(
        model=responses.field(terminal, "model", model),
        delta=LLMResultChunkDelta(
            index=0,
            message=AssistantPromptMessage(
                content="",
                tool_calls=calls,
                opaque_body=None if buffer.stopped else responses.opaque(terminal),
            ),
            finish_reason=finish_reason,
            usage=responses.usage(
                llm,
                model,
                credentials,
                prompt_messages,
                tools,
                terminal,
                canonical or formatted,
                calls,
            ),
        ),
    )


class StopBuffer:
    def __init__(self, stop: list[str] | None) -> None:
        self.tokens = [token for token in stop or [] if token]
        self.keep = max((len(token) for token in self.tokens), default=1) - 1
        self.pending = ""
        self.stopped = False

    def push(self, value: str) -> str:
        if self.stopped or not value:
            return ""
        if not self.tokens:
            return value
        self.pending += value
        positions = [self.pending.find(token) for token in self.tokens]
        positions = [position for position in positions if position >= 0]
        if positions:
            result = self.pending[: min(positions)]
            self.pending = ""
            self.stopped = True
            return result
        emit = len(self.pending) - self.keep
        if emit <= 0:
            return ""
        result, self.pending = self.pending[:emit], self.pending[emit:]
        return result

    def finish(self) -> str:
        if self.stopped:
            return ""
        result, self.pending = self.pending, ""
        return result


def track_call(fragments: dict[int, dict[str, Any]], event: Any) -> None:
    event_type = responses.field(event, "type", "")
    index = responses.field(event, "output_index", -1)
    item = responses.field(event, "item")
    if (
        event_type.startswith("response.output_item")
        and responses.field(item, "type") != "function_call"
    ):
        return
    fragment = fragments.setdefault(
        index,
        {"id": "", "name": "", "arguments": "", "done": False},
    )
    if item is not None:
        fragment["id"] = (
            responses.field(item, "call_id", fragment["id"]) or fragment["id"]
        )
        fragment["name"] = (
            responses.field(item, "name", fragment["name"]) or fragment["name"]
        )
        fragment["arguments"] = (
            responses.field(item, "arguments", fragment["arguments"])
            or fragment["arguments"]
        )
        fragment["done"] = event_type.endswith(".done") and responses.field(
            item, "status"
        ) in (None, "completed")
    elif event_type.endswith(".delta"):
        fragment["arguments"] += responses.field(event, "delta", "") or ""
    elif event_type.endswith(".done"):
        fragment["arguments"] = (
            responses.field(event, "arguments", fragment["arguments"])
            or fragment["arguments"]
        )
        fragment["done"] = True


def fragment_calls(
    fragments: dict[int, dict[str, Any]],
) -> list[AssistantPromptMessage.ToolCall]:
    return [
        responses.make_call(item["id"], item["name"], item["arguments"])
        for _, item in sorted(fragments.items())
        if item["done"]
    ]


def chunk(model: str, value: str) -> LLMResultChunk:
    return LLMResultChunk(
        model=model,
        delta=LLMResultChunkDelta(
            index=0,
            message=AssistantPromptMessage(content=value),
        ),
    )
