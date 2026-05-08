from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any, Optional, Union, cast

import requests
from dify_plugin import LargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContent,
    PromptMessageContentType,
    PromptMessageFunction,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError

from ..common_telnyx import _CommonTelnyx


class TelnyxLargeLanguageModel(_CommonTelnyx, LargeLanguageModel):
    """Telnyx chat-completions model."""

    CHAT_COMPLETIONS_PATH = "/v2/ai/chat/completions"

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator[LLMResultChunk, None, None]]:
        payload = self._build_payload(
            model=model,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )
        response = self._post_json(credentials, self.CHAT_COMPLETIONS_PATH, payload, stream=stream)
        if response.encoding is None or response.encoding == "ISO-8859-1":
            response.encoding = "utf-8"
        if stream:
            return self._handle_stream_response(model, credentials, response, prompt_messages)
        return self._handle_response(model, credentials, response, prompt_messages)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
                "stream": False,
            }
            response = self._post_json(credentials, self.CHAT_COMPLETIONS_PATH, payload)
            data = response.json()
            if not data.get("choices"):
                raise CredentialsValidateFailedError("Telnyx validation response returned no choices")
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        return self._num_tokens_from_messages(prompt_messages, credentials=credentials, tools=tools)

    def _build_payload(
        self,
        *,
        model: str,
        prompt_messages: list[PromptMessage],
        model_parameters: dict | None,
        tools: Optional[list[PromptMessageTool]],
        stop: Optional[list[str]],
        stream: bool,
        user: Optional[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [self._convert_prompt_message_to_dict(message) for message in prompt_messages],
            "stream": stream,
        }
        if model_parameters:
            payload.update({k: v for k, v in model_parameters.items() if v is not None})
        if stop:
            payload["stop"] = stop
        if user:
            payload["user"] = user
        if tools:
            payload["tool_choice"] = "auto"
            payload["tools"] = [PromptMessageFunction(function=tool).model_dump() for tool in tools]
        return payload

    def _handle_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise InvokeError("LLM response returned no choices")

        choice = choices[0]
        message_data = choice.get("message") or {}
        content = message_data.get("content") or ""
        assistant_message = AssistantPromptMessage(content=content, tool_calls=[])
        if tool_calls := message_data.get("tool_calls"):
            assistant_message.tool_calls = self._extract_response_tool_calls(tool_calls)

        usage_data = data.get("usage") or {}
        prompt_tokens = usage_data.get("prompt_tokens")
        completion_tokens = usage_data.get("completion_tokens")
        if prompt_tokens is None:
            prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
        if completion_tokens is None:
            completion_tokens = self._num_tokens_from_string(content)

        usage = self._calc_response_usage(model, credentials, int(prompt_tokens), int(completion_tokens))
        return LLMResult(
            model=data.get("model") or model,
            prompt_messages=prompt_messages,
            message=assistant_message,
            usage=usage,
        )

    def _handle_stream_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator[LLMResultChunk, None, None]:
        full_content = ""
        usage_data: dict[str, Any] = {}
        finish_reason = ""
        index = 0

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line.removeprefix("data:").strip()
            if line == "[DONE]":
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage_data = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            content = delta.get("content") or ""
            if not content:
                continue
            index += 1
            full_content += content
            yield LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(
                    index=index,
                    message=AssistantPromptMessage(content=content),
                ),
            )

        prompt_tokens = usage_data.get("prompt_tokens")
        completion_tokens = usage_data.get("completion_tokens")
        if prompt_tokens is None:
            prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
        if completion_tokens is None:
            completion_tokens = self._num_tokens_from_string(full_content)
        usage = self._calc_response_usage(model, credentials, int(prompt_tokens), int(completion_tokens))
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=index + 1,
                message=AssistantPromptMessage(content=""),
                finish_reason=finish_reason,
                usage=usage,
            ),
        )

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict[str, Any]:
        if isinstance(message, UserPromptMessage):
            if isinstance(message.content, str):
                message_dict: dict[str, Any] = {"role": "user", "content": message.content}
            else:
                content = []
                for item in message.content or []:
                    if item.type == PromptMessageContentType.TEXT:
                        text_item = cast(PromptMessageContent, item)
                        content.append({"type": "text", "text": text_item.data})
                    elif item.type == PromptMessageContentType.IMAGE:
                        image_item = cast(ImagePromptMessageContent, item)
                        content.append({"type": "image_url", "image_url": {"url": image_item.data}})
                message_dict = {"role": "user", "content": content}
        elif isinstance(message, AssistantPromptMessage):
            message_dict = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                message_dict["tool_calls"] = [tool_call.model_dump() for tool_call in message.tool_calls]
        elif isinstance(message, SystemPromptMessage):
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message_dict = {
                "role": "tool",
                "content": message.content,
                "tool_call_id": message.tool_call_id,
            }
        else:
            raise ValueError(f"Unsupported prompt message type: {type(message)}")

        if getattr(message, "name", None) and message_dict.get("role") != "tool":
            message_dict["name"] = message.name
        return message_dict

    @staticmethod
    def _extract_response_tool_calls(tool_calls: list[dict[str, Any]]) -> list[AssistantPromptMessage.ToolCall]:
        extracted = []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            extracted.append(
                AssistantPromptMessage.ToolCall(
                    id=tool_call.get("id") or "",
                    type=tool_call.get("type") or "function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=function.get("name") or "",
                        arguments=function.get("arguments") or "",
                    ),
                )
            )
        return extracted

    def _num_tokens_from_string(self, text: str) -> int:
        try:
            return self._get_num_tokens_by_gpt2(text)
        except Exception:
            return max(1, len(text) // 4) if text else 0

    def _num_tokens_from_messages(
        self,
        messages: list[PromptMessage],
        *,
        credentials: Optional[dict] = None,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        text = ""
        for message in messages:
            converted = self._convert_prompt_message_to_dict(message)
            text += json.dumps(converted, ensure_ascii=False)
        token_count = self._num_tokens_from_string(text)
        if tools:
            token_count += self._num_tokens_from_string(json.dumps([tool.model_dump() for tool in tools]))
        return token_count
