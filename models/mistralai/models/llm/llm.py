import logging
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

from models.llm._metadata import apply_dify_headers_if_enabled

logger = logging.getLogger(__name__)


def _split_content_chunks(chunks: list) -> tuple[str, str]:
    """Split Mistral content chunks into (reasoning text, answer text).

    Reasoning models return ``content`` as a list such as
    ``[{"type": "thinking", "thinking": [{"type": "text", "text": ...}]},
    {"type": "text", "text": ...}]``. Unknown chunk types are skipped.
    """
    reasoning: list[str] = []
    answer: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_type = chunk.get("type")
        if chunk_type == "thinking":
            thinking = chunk.get("thinking")
            if isinstance(thinking, str):
                reasoning.append(thinking)
            elif isinstance(thinking, list):
                for part in thinking:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        reasoning.append(part["text"])
        elif chunk_type == "text":
            if isinstance(chunk.get("text"), str):
                answer.append(chunk["text"])
        else:
            logger.debug("Skipping unsupported Mistral content chunk type: %s", chunk_type)
    return "".join(reasoning), "".join(answer)


class _NormalizedJSONResponse:
    """Wraps a response so that ``json()`` returns an already-normalized payload."""

    def __init__(self, response: requests.Response, payload: dict) -> None:
        self._response = response
        self._payload = payload

    def json(self, **kwargs: Any) -> dict:
        return self._payload

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)


class MistralAILargeLanguageModel(OAICompatLargeLanguageModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        self._add_custom_parameters(credentials)
        apply_dify_headers_if_enabled(credentials)

        # Transform reasoning_mode to prompt_mode for Magistral models
        if "magistral" in model.lower() and "reasoning_mode" in model_parameters:
            reasoning_enabled = model_parameters.pop("reasoning_mode")
            if reasoning_enabled:
                model_parameters["prompt_mode"] = "reasoning"
            else:
                model_parameters["prompt_mode"] = None

        stop = []
        user = None
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        apply_dify_headers_if_enabled(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        credentials["mode"] = "chat"
        credentials["endpoint_url"] = "https://api.mistral.ai/v1"

    def _wrap_thinking_by_reasoning_content(
        self, delta: dict, is_reasoning: bool
    ) -> tuple[str, bool]:
        content = delta.get("content")
        if not isinstance(content, list):
            return super()._wrap_thinking_by_reasoning_content(delta, is_reasoning)

        reasoning, answer = _split_content_chunks(content)
        if (
            not reasoning
            and not answer
            and not delta.get("tool_calls")
            and not delta.get("function_call")
        ):
            # Nothing renderable (empty list / unknown chunks): keep the reasoning state as-is.
            return "", is_reasoning

        normalized = {**delta, "content": answer}
        if reasoning:
            normalized["reasoning_content"] = (delta.get("reasoning_content") or "") + reasoning
        return super()._wrap_thinking_by_reasoning_content(normalized, is_reasoning)

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        payload = response.json()
        for choice in payload.get("choices") or []:
            message = choice.get("message") if isinstance(choice, dict) else None
            if isinstance(message, dict) and isinstance(message.get("content"), list):
                reasoning, answer = _split_content_chunks(message["content"])
                if reasoning:
                    answer = "<think>\n" + reasoning + "\n</think>" + answer
                message["content"] = answer
        return super()._handle_generate_response(
            model, credentials, _NormalizedJSONResponse(response, payload), prompt_messages
        )
