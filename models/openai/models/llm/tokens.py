from __future__ import annotations

import json
import logging

import tiktoken

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    TextPromptMessageContent,
)

logger = logging.getLogger(__name__)


def count_text(model: str, text: str) -> int:
    """Return a stable local estimate when OpenAI does not report usage."""
    try:
        encoding = tiktoken.encoding_for_model(_base_model(model))
    except KeyError:
        logger.debug("No tiktoken mapping for %s; using o200k_base", model)
        encoding = tiktoken.get_encoding("o200k_base")
    return len(encoding.encode(text))


def count_messages(
    model: str,
    messages: list[PromptMessage],
    tools: list[PromptMessageTool] | None = None,
) -> int:
    """Estimate message tokens without pretending to reproduce server accounting."""
    parts: list[str] = []
    for message in messages:
        parts.extend((message.role.value, message.name or "", _text(message)))
        if isinstance(message, AssistantPromptMessage):
            for call in message.tool_calls:
                parts.extend((call.id, call.function.name, call.function.arguments))

    if tools:
        parts.append(
            json.dumps(
                [tool.model_dump(mode="json") for tool in tools],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    # The fixed overhead is deliberately approximate. API usage is authoritative.
    return count_text(model, "\n".join(parts)) + 3 * len(messages) + 3


def _text(message: PromptMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        item.data
        for item in message.content or []
        if isinstance(item, TextPromptMessageContent)
    )


def _base_model(model: str) -> str:
    return model.split(":", 2)[1] if model.startswith("ft:") else model
