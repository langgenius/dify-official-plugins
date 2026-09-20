import json
from collections.abc import Generator
from typing import cast

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import (
    LLMMode,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContent,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError


class StepfunLargeLanguageModel(OAICompatLargeLanguageModel):
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
        self._add_function_call(model, credentials)
        if model in {"step-3.7-flash", "step-5-preview"}:
            model_parameters = {
                **model_parameters,
                "reasoning_format": "deepseek-style",
            }
        user = user[:32] if user else None
        # Optional: attach Dify app_id as request headers. Default disabled;
        # opt-in via the enable_request_metadata credential. Routed through
        # extra_headers because the SDK's OAICompat base class does not
        # forward body-level metadata. No-op when disabled or when the
        # Dify session does not expose an app_id.
        from ._metadata import apply_dify_headers_if_enabled

        credentials = apply_dify_headers_if_enabled(credentials)
        return super()._invoke(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        try:
            super().validate_credentials(model, credentials)
        except CredentialsValidateFailedError as ex:
            # api.stepfun.com and api.stepfun.ai return byte-identical 401
            # bodies, so the error must say which endpoint rejected the key.
            raise CredentialsValidateFailedError(
                f"{ex} (endpoint validated: {credentials.get('endpoint_url', 'unknown')})"
            ) from ex

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity | None:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
                if credentials.get("function_calling_type") == "tool_call"
                else []
            ),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 8000)),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_us="Temperature", zh_hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens", 1024)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
            ],
        )

    def _add_custom_parameters(self, credentials: dict) -> None:
        credentials["mode"] = "chat"
        if credentials.get("use_international_endpoint", "false") == "true":
            credentials["endpoint_url"] = "https://api.stepfun.ai/v1"
        else:
            credentials["endpoint_url"] = "https://api.stepfun.com/v1"

    def _add_function_call(self, model: str, credentials: dict) -> None:
        model_schema = self.get_model_schema(model, credentials)
        if model_schema and {
            ModelFeature.TOOL_CALL,
            ModelFeature.MULTI_TOOL_CALL,
        }.intersection(model_schema.features or []):
            credentials["function_calling_type"] = "tool_call"

    def _convert_prompt_message_to_dict(
        self, message: PromptMessage, credentials: dict | None = None
    ) -> dict:
        """
        Convert PromptMessage to dict for OpenAI API format
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            else:
                sub_messages = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(PromptMessageContent, message_content)
                        sub_message_dict = {
                            "type": "text",
                            "text": message_content.data,
                        }
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_content = cast(ImagePromptMessageContent, message_content)
                        sub_message_dict = {
                            "type": "image_url",
                            "image_url": {
                                "url": message_content.data,
                                "detail": message_content.detail.value,
                            },
                        }
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.VIDEO:
                        message_content = cast(PromptMessageContent, message_content)
                        sub_message_dict = {
                            "type": "video_url",
                            "video_url": {"url": message_content.data},
                        }
                        sub_messages.append(sub_message_dict)
                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                message_dict["tool_calls"] = []
                for function_call in message.tool_calls:
                    message_dict["tool_calls"].append(
                        {
                            "id": function_call.id,
                            "type": function_call.type,
                            "function": {
                                "name": function_call.function.name,
                                "arguments": function_call.function.arguments,
                            },
                        }
                    )
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {
                "role": "tool",
                "content": message.content,
                "tool_call_id": message.tool_call_id,
            }
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        else:
            raise TypeError(f"Got unknown type {message}")
        if message.name:
            message_dict["name"] = message.name
        return message_dict

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        # Like Moonshot, preserve reasoning for non-streaming callers too.
        result = super()._handle_generate_response(model, credentials, response, prompt_messages)
        message = response.json()["choices"][0].get("message", {})
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if reasoning:
            result.message.content = f"<think>{reasoning}</think>{result.message.content or ''}"
            result.message.opaque_body = {"reasoning_content": reasoning}
        return result

    def _wrap_thinking_by_reasoning_content(
        self, delta: dict, is_reasoning: bool
    ) -> tuple[str, bool]:
        # Tongyi/Moonshot's transition handling also covers a chunk containing
        # both the last reasoning token and the first answer token.
        content = delta.get("content") or ""
        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
        output = ""
        if reasoning:
            output = reasoning if is_reasoning else "<think>" + reasoning
            is_reasoning = True
        if is_reasoning and (content or delta.get("tool_calls")):
            output += "</think>"
            is_reasoning = False
        return output + content, is_reasoning

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        full_content = ""
        usage = {}
        tool_calls = {}
        finish_reason = None
        is_reasoning = False
        index = 0

        # Split on lines so both LF and CRLF SSE streams work. StepFun sends
        # one JSON object per data line; comments and empty lines are keepalives.
        for line in response.iter_lines(decode_unicode=True):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("error"):
                raise ValueError(chunk["error"])
            if chunk.get("usage"):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {"content": choice.get("text", "")}
            content, is_reasoning = self._wrap_thinking_by_reasoning_content(delta, is_reasoning)
            for part in delta.get("tool_calls") or []:
                # Index, not function name, identifies a call: parallel calls
                # may invoke the same function and interleave their arguments.
                call = tool_calls.setdefault(
                    part.get("index", 0),
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if part.get("id"):
                    call["id"] = part["id"]
                if part.get("type"):
                    call["type"] = part["type"]
                for key in ("name", "arguments"):
                    call["function"][key] += (part.get("function") or {}).get(key) or ""
            if content:
                full_content += content
                yield LLMResultChunk(
                    model=model,
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=AssistantPromptMessage(content=content),
                    ),
                )
                index += 1

        if is_reasoning:
            full_content += "</think>"
            yield LLMResultChunk(
                model=model,
                delta=LLMResultChunkDelta(
                    index=index,
                    message=AssistantPromptMessage(content="</think>"),
                ),
            )
            index += 1
        if tool_calls:
            yield LLMResultChunk(
                model=model,
                delta=LLMResultChunkDelta(
                    index=index,
                    message=AssistantPromptMessage(
                        content="",
                        tool_calls=self._extract_response_tool_calls(
                            [tool_calls[k] for k in sorted(tool_calls)]
                        ),
                    ),
                ),
            )
            index += 1
        prompt_tokens = usage.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
        completion_tokens = usage.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = self._num_tokens_from_string(
                text=full_content + json.dumps(list(tool_calls.values()), ensure_ascii=False)
            )
        yield LLMResultChunk(
            model=model,
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=""),
                finish_reason=finish_reason,
                usage=self._calc_response_usage(
                    model, credentials, prompt_tokens, completion_tokens
                ),
            ),
        )
