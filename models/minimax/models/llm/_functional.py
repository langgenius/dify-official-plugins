"""Pure transformations used by the MiniMax LLM adapter.

Keep provider I/O in ``llm.py`` and put deterministic data-to-data operations here.
This makes the adapter easier to reason about, compose, and test without an API client.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import chain, groupby
from types import MappingProxyType
from typing import Any

from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    VideoPromptMessageContent,
)

MODEL_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "minimax-m3": "MiniMax-M3",
        "minimax-m2.7": "MiniMax-M2.7",
        "minimax-m2.7-highspeed": "MiniMax-M2.7-highspeed",
        "minimax-m2.7lightning": "MiniMax-M2.7-highspeed",
        "minimax-m2.7-lightning": "MiniMax-M2.7-highspeed",
        "minimax-m2.5": "MiniMax-M2.5",
        "minimax-m2.5lightning": "MiniMax-M2.5-highspeed",
        "minimax-m2.5-lightning": "MiniMax-M2.5-highspeed",
        "minimax-m2.1": "MiniMax-M2.1",
        "minimax-m2.1-lightning": "MiniMax-M2.1-highspeed",
        "minimax-m2": "MiniMax-M2",
        "minimax-m2-her": "MiniMax-M2",
        "minimax-m1": "MiniMax-M2.5",
    }
)

FINISH_REASONS: Mapping[str, str] = MappingProxyType(
    {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "tool_use": "tool_calls"}
)

MEDIA_KINDS: Mapping[str, str] = MappingProxyType(
    {
        "image": "image",
        "image_url": "image",
        "video": "video",
        "video_url": "video",
        "document": "document",
        "document_url": "document",
    }
)

MEDIA_CONTENT_TYPES = (
    (ImagePromptMessageContent, "image"),
    (VideoPromptMessageContent, "video"),
    (DocumentPromptMessageContent, "document"),
)


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    """Normalized generation policy, independent of SDK request objects."""

    max_tokens: int
    thinking: Any
    thinking_budget: int
    exclude_reasoning_tokens: bool
    sampling: tuple[tuple[str, Any], ...]


def resolve_model_name(model: str) -> str:
    return MODEL_ALIASES.get(model, MODEL_ALIASES.get(model.lower(), model))


def generation_options(parameters: Mapping[str, Any], request_model: str) -> GenerationOptions:
    """Normalize parameters without changing the caller-owned mapping."""

    values = dict(parameters)
    raw_max_tokens = next(
        (
            values[name]
            for name in ("max_tokens", "max_tokens_to_sample", "max_output_tokens")
            if name in values
        ),
        1024,
    )
    max_tokens = int(raw_max_tokens or 1024)

    return GenerationOptions(
        max_tokens=max_tokens if max_tokens > 0 else 1024,
        thinking=values.get("thinking"),
        thinking_budget=int(values.get("thinking_budget", 1024) or 1024),
        exclude_reasoning_tokens=(
            values.get("exclude_reasoning_tokens", request_model == "MiniMax-M3") is True
        ),
        sampling=tuple(
            (name, values[name])
            for name in ("temperature", "top_p", "top_k")
            if values.get(name) is not None
        ),
    )


def normalize_thinking_payload(
    *, thinking: Any, thinking_budget: int, request_model: str
) -> dict[str, Any] | None:
    if isinstance(thinking, dict):
        return dict(thinking)

    thinking_type = thinking.strip().lower() if isinstance(thinking, str) else thinking
    if thinking_type == "adaptive":
        return {"type": "adaptive"}
    if thinking_type is True or thinking_type in ("enabled", "true"):
        if request_model == "MiniMax-M3":
            return {"type": "adaptive"}
        return {"type": "enabled", "budget_tokens": max(1024, thinking_budget)}
    return None


def content_type_value(content_type: Any) -> Any:
    return getattr(content_type, "value", content_type)


def _nested_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return str(value.get("url") or "")
    return ""


def _mapping_media_data(content: Mapping[str, Any], media_kind: str) -> str:
    direct = content.get("data") or content.get("url")
    return str(direct) if direct else _nested_url(content.get(f"{media_kind}_url"))


def media_source(data: str) -> dict[str, Any]:
    if data.startswith("data:") and ";base64," in data:
        header, encoded = data.split(";base64,", 1)
        return {"type": "base64", "media_type": header.removeprefix("data:"), "data": encoded}
    return {"type": "url", "url": data}


def user_content_block(content: Any) -> dict[str, Any] | None:
    """Convert one Dify content value into one MiniMax content block."""

    if isinstance(content, TextPromptMessageContent):
        return {"type": "text", "text": content.data}

    for content_class, media_kind in MEDIA_CONTENT_TYPES:
        if isinstance(content, content_class):
            data = content.data.strip()
            return {"type": media_kind, "source": media_source(data)} if data else None

    if isinstance(content, Mapping):
        content_kind = content_type_value(content.get("type"))
        if content_kind == "text":
            return {"type": "text", "text": str(content.get("data") or content.get("text") or "")}
        if media_kind := MEDIA_KINDS.get(content_kind):
            data = _mapping_media_data(content, media_kind).strip()
            return {"type": media_kind, "source": media_source(data)} if data else None
        return None

    content_kind = content_type_value(getattr(content, "type", None))
    if content_kind == "text":
        return {"type": "text", "text": str(getattr(content, "data", ""))}
    if media_kind := MEDIA_KINDS.get(content_kind):
        data = str(getattr(content, "data", "")).strip()
        return {"type": media_kind, "source": media_source(data)} if data else None
    return None


def normalize_content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)]
    return []


def merge_consecutive_messages(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group adjacent messages by role without mutating any input message."""

    return [
        {
            "role": role,
            "content": list(
                chain.from_iterable(
                    normalize_content_blocks(message.get("content")) for message in group
                )
            ),
        }
        for role, group in groupby(messages, key=lambda message: message.get("role"))
    ]


def text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    def text_fragment(item: Any) -> str:
        if isinstance(item, TextPromptMessageContent):
            return item.data
        if isinstance(item, Mapping) and content_type_value(item.get("type")) == "text":
            return str(item.get("data") or item.get("text") or "")
        if content_type_value(getattr(item, "type", None)) == "text":
            return str(getattr(item, "data", getattr(item, "text", "")))
        return ""

    return " ".join(filter(None, map(text_fragment, content)))


def parse_json_object(arguments: str) -> dict[str, Any]:
    try:
        value = json.loads(arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return {"raw": arguments}
    return value if isinstance(value, dict) else {"value": value}


def render_assistant_text(
    thinking_blocks: Sequence[Mapping[str, Any]], text_chunks: Sequence[str], *, hide_thinking: bool
) -> str:
    answer = "".join(text_chunks)
    if hide_thinking:
        return answer

    thinking = "".join(
        (
            str(block.get("thinking", ""))
            if block.get("type") == "thinking"
            else "[Redacted thinking]" if block.get("type") == "redacted_thinking" else ""
        )
        for block in thinking_blocks
    )
    return f"<think>{thinking}</think>\n{answer}" if thinking else answer


def normalize_anthropic_endpoint(endpoint_url: Any) -> str:
    endpoint = str(endpoint_url or "https://api.minimax.io").strip()
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    endpoint = endpoint.rstrip("/")
    return endpoint if endpoint.endswith("/anthropic") else f"{endpoint}/anthropic"


def convert_finish_reason(finish_reason: str | None) -> str | None:
    return FINISH_REASONS.get(finish_reason, finish_reason) if finish_reason else None


def index_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)
