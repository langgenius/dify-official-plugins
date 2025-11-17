from typing import Any, Mapping, Optional, Sequence, Union, Tuple, Generator, Callable
import logging

from openai import OpenAI
from httpx import Timeout
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)

logger = logging.getLogger(__name__)


class AihubmixOpenAIResponses:
    def __init__(self, credentials: Mapping[str, Any]):
        self.client = OpenAI(**self._to_credential_kwargs(credentials))
        self.credentials = dict(credentials)

    def _to_credential_kwargs(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        # Align with aihubmix provider style (see anthropic.py)
        return {
            "api_key": credentials["api_key"],
            "base_url": "https://aihubmix.com/v1",
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }

    def _convert_messages_to_responses_input(self, prompt_messages: Sequence[PromptMessage]) -> str:
        role_map = {
            UserPromptMessage: "user",
            AssistantPromptMessage: "assistant",
            ToolPromptMessage: "tool",
        }
        input_parts: list[str] = []
        for m in prompt_messages:
            role = role_map.get(type(m))
            if not role:
                continue

            content_str = ""
            if isinstance(m.content, str):
                content_str = m.content
            elif isinstance(m.content, list):
                content_str = "\n".join(
                    [item.data for item in m.content if item.type == PromptMessageContentType.TEXT]
                )

            if content_str:
                input_parts.append(f"{role}: {content_str}")
        return "\n\n".join(input_parts)

    def create_raw(
        self,
        *,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        user: Optional[str] = None,
    ) -> Tuple[Any, str]:
        params = dict(model_parameters)
        if "max_completion_tokens" in params:
            params["max_output_tokens"] = params.pop("max_completion_tokens")
        if user:
            params["user"] = user

        final_input = self._convert_messages_to_responses_input(prompt_messages)
        logger.info(f"Aihubmix Responses API Request: model={model} params={params}")

        resp_obj = self.client.responses.create(
            model=model,
            input=final_input,
            extra_headers={"APP-Code": "Dify2025"},
            **params
        )
        text_content = resp_obj.output_text or ""
        return resp_obj, text_content

    def stream_raw(
        self,
        *,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        user: Optional[str] = None,
    ) -> Generator[Tuple[str, Mapping[str, Any]], None, None]:
        """
        Yield tuple(kind, payload):
        - ("delta", {"text": str}) for incremental text
        - ("final", {"response": Response, "text": str}) at completion
        """
        params = dict(model_parameters)
        if "max_completion_tokens" in params:
            params["max_output_tokens"] = params.pop("max_completion_tokens")
        if user:
            params["user"] = user

        final_input = self._convert_messages_to_responses_input(prompt_messages)
        logger.info(f"Aihubmix Responses API Stream Request: model={model} params={params}")

        with self.client.responses.stream(
            model=model,
            input=final_input,
            extra_headers={"APP-Code": "Dify2025"},
            **params
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)
                if etype == "response.output_text.delta":
                    delta_text = getattr(event, "delta", "") or ""
                    if delta_text:
                        yield ("delta", {"text": delta_text})
                elif etype == "response.completed":
                    final = stream.get_final_response()
                    full_text = getattr(final, "output_text", None) or ""
                    yield ("final", {"response": final, "text": full_text})
                    break
                elif etype == "response.error":
                    # Surface error immediately
                    err = getattr(event, "error", None)
                    message = (getattr(err, "message", None) or str(err)) if err else "Responses stream error"
                    raise RuntimeError(message)

    def create_llm_result(
        self,
        *,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        compute_usage: Callable[[int, int], Mapping[str, Any]],
        user: Optional[str] = None,
    ) -> LLMResult:
        resp_obj, text_content = self.create_raw(
            model=model,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            user=user,
        )
        assistant_prompt_message = AssistantPromptMessage(content=text_content)

        prompt_tokens = 0
        completion_tokens = 0
        if getattr(resp_obj, "usage", None):
            prompt_tokens = getattr(resp_obj.usage, "input_tokens", 0) or 0
            completion_tokens = getattr(resp_obj.usage, "output_tokens", 0) or 0

        usage = compute_usage(prompt_tokens, completion_tokens)

        result = LLMResult(
            model=getattr(resp_obj, "model", model),
            prompt_messages=list(prompt_messages),
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=None,
        )
        return result

    def stream_llm_chunks(
        self,
        *,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        compute_usage: Callable[[int, int], Mapping[str, Any]],
        user: Optional[str] = None,
    ) -> Generator[LLMResultChunk, None, None]:
        full_text = ""
        index = 0
        final_response = None
        for kind, payload in self.stream_raw(
            model=model,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            user=user,
        ):
            if kind == "delta":
                delta_text = payload.get("text", "")
                if not delta_text:
                    continue
                full_text += delta_text
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=AssistantPromptMessage(content=delta_text),
                    ),
                )
                index += 1
            elif kind == "final":
                final_response = payload.get("response")
                break

        prompt_tokens = 0
        completion_tokens = 0
        if final_response and getattr(final_response, "usage", None):
            prompt_tokens = getattr(final_response.usage, "input_tokens", 0) or 0
            completion_tokens = getattr(final_response.usage, "output_tokens", 0) or 0

        usage = compute_usage(prompt_tokens, completion_tokens)

        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=""),
                finish_reason="stop",
                usage=usage,
            ),
        )
