"""OpenCode Go LLM provider — single entry that routes chat / Anthropic / Responses.

dify_plugin registers one LargeLanguageModel class per ModelType (last source
wins), so protocol selection must live inside this class rather than three
model_sources.
"""

from __future__ import annotations

import logging
from collections.abc import Generator, Mapping
from typing import Any, Optional, Union

import requests
from dify_plugin import OAICompatLargeLanguageModel, get_current_session
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
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeError,
)

try:
    from models.llm import llm_anthropic, llm_responses, session_headers
    from models.llm.session_headers import (
        DEFAULT_ENDPOINT_URL,
        DEFAULT_USER_AGENT,
        ANTHROPIC_MODELS,
        RESPONSES_MODELS,
        _RUN_ID_HEADER,
        add_custom_parameters,
        apply_extra_headers,
        build_session_id,
        current_conversation_id,
        current_rpc_session_id,
        extra_headers_rule,
        is_resolved_id,
        join_endpoint_url,
        parse_extra_headers,
        public_headers_for_protocol,
        resolve_protocol,
    )
except ImportError:  # pragma: no cover - importlib standalone load
    import llm_anthropic
    import llm_responses
    import session_headers
    from session_headers import (
        DEFAULT_ENDPOINT_URL,
        DEFAULT_USER_AGENT,
        ANTHROPIC_MODELS,
        RESPONSES_MODELS,
        _RUN_ID_HEADER,
        add_custom_parameters,
        apply_extra_headers,
        build_session_id,
        current_conversation_id,
        current_rpc_session_id,
        extra_headers_rule,
        is_resolved_id,
        join_endpoint_url,
        parse_extra_headers,
        public_headers_for_protocol,
        resolve_protocol,
    )

logger = logging.getLogger(__name__)

# Back-compat aliases (tests and older imports).
_extra_headers_rule = extra_headers_rule


class OpenCodeGoLargeLanguageModel(OAICompatLargeLanguageModel):
    @staticmethod
    def _inject_extra_headers_rule(entity: AIModelEntity) -> AIModelEntity:
        if not any(rule.name == "extra_headers" for rule in entity.parameter_rules):
            entity.parameter_rules.append(extra_headers_rule())
        return entity

    def predefined_models(self) -> list[AIModelEntity]:
        return [self._inject_extra_headers_rule(m) for m in super().predefined_models()]

    def get_model_schema(
        self, model: str, credentials: Optional[dict] = None
    ) -> Optional[AIModelEntity]:
        schema = super().get_model_schema(model, credentials)
        return self._inject_extra_headers_rule(schema) if schema else None

    # --- session helpers kept as classmethods so existing tests can call them ---
    @staticmethod
    def _parse_extra_headers(raw: Any) -> dict[str, str]:
        return parse_extra_headers(raw)

    @classmethod
    def _apply_extra_headers(cls, credentials: dict, model_parameters: dict) -> None:
        apply_extra_headers(credentials, model_parameters)

    @classmethod
    def _current_conversation_id(cls) -> Optional[str]:
        return current_conversation_id()

    @classmethod
    def _current_rpc_session_id(cls) -> Optional[str]:
        return current_rpc_session_id()

    @staticmethod
    def _is_resolved_id(value: str) -> bool:
        return is_resolved_id(value)

    @classmethod
    def _build_session_id(cls, user: Optional[str], credentials: dict) -> str:
        return build_session_id(user, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict, user: Optional[str]) -> None:
        add_custom_parameters(credentials, user)

    @classmethod
    def _resolve_protocol(cls, model: str, credentials: dict) -> str:
        return resolve_protocol(model, credentials)

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
    ) -> Union[LLMResult, Generator]:
        self._apply_extra_headers(credentials, model_parameters)
        headers = add_custom_parameters(credentials, user)
        protocol = self._resolve_protocol(model, credentials)
        if protocol == "anthropic":
            return self._invoke_anthropic(
                model,
                credentials,
                prompt_messages,
                model_parameters,
                tools,
                stop,
                stream,
                headers,
            )
        if protocol == "responses":
            return self._invoke_responses(
                model,
                credentials,
                prompt_messages,
                model_parameters,
                tools,
                stop,
                stream,
                headers,
            )
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
        credentials = dict(credentials)
        add_custom_parameters(credentials, user=None)
        protocol = self._resolve_protocol(model, credentials)
        try:
            if protocol == "anthropic":
                self._validate_anthropic_credentials(model, credentials)
            elif protocol == "responses":
                self._validate_responses_credentials(model, credentials)
            else:
                super().validate_credentials(model, credentials)
        except CredentialsValidateFailedError:
            raise
        except InvokeError as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        add_custom_parameters(credentials, user=None)
        features: list[ModelFeature] = []
        if credentials.get("function_calling_type", "tool_call") == "tool_call":
            features.extend(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
            )
        if credentials.get("vision_support", "false") == "true":
            features.append(ModelFeature.VISION)

        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=features,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 262144)
                ),
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
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=4096,
                    min=1,
                    max=int(credentials.get("max_tokens", 32768)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大 Token"),
                    type=ParameterType.INT,
                ),
                extra_headers_rule(),
            ],
        )
        return self._inject_extra_headers_rule(entity)

    # ------------------------------------------------------------------
    # Anthropic Messages
    # ------------------------------------------------------------------
    def _anthropic_headers(self, credentials: dict, headers: dict[str, str]) -> dict[str, str]:
        api_key = str(credentials.get("api_key") or "")
        return public_headers_for_protocol(headers, api_key, "anthropic")

    def _anthropic_url(self, credentials: dict) -> str:
        base = credentials.get("endpoint_url") or DEFAULT_ENDPOINT_URL
        return join_endpoint_url(base, "messages")

    def _build_anthropic_body(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        stream: bool,
    ) -> dict[str, Any]:
        system, messages = llm_anthropic.build_messages_payload(prompt_messages)
        body: dict[str, Any] = {
            "model": credentials.get("endpoint_model_name") or model,
            "messages": messages,
            "stream": bool(stream),
            **llm_anthropic.filter_model_parameters(model_parameters),
        }
        if system:
            body["system"] = system
        tool_payload = llm_anthropic.build_tools_payload(tools)
        if tool_payload:
            body["tools"] = tool_payload
        return body

    def _invoke_anthropic(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        stop: Optional[list[str]],
        stream: bool,
        headers: dict[str, str],
    ):
        body = self._build_anthropic_body(
            model, credentials, prompt_messages, model_parameters, tools, stream
        )
        if stop:
            body["stop_sequences"] = list(stop)
        try:
            response = requests.post(
                self._anthropic_url(credentials),
                headers=self._anthropic_headers(credentials, headers),
                json=body,
                stream=stream,
                timeout=(10, 600),
            )
        except requests.RequestException as ex:
            raise InvokeError(
                f"OpenCode Anthropic Messages connection error: {ex}"
            ) from ex

        if response.status_code != 200:
            raise llm_anthropic.map_http_error(response, response.text)

        if stream:
            return self._wrap_anthropic_stream(model, credentials, prompt_messages, response)

        data = response.json()
        text, tool_calls, in_tok, out_tok, stop_reason = (
            llm_anthropic.parse_non_stream_response(data)
        )
        assistant = AssistantPromptMessage(content=text, tool_calls=tool_calls or [])
        usage = self._calc_response_usage(model, credentials, in_tok, out_tok)
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant,
            usage=usage,
            system_fingerprint=data.get("id"),
        )

    def _wrap_anthropic_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        response: requests.Response,
    ) -> Generator[LLMResultChunk, None, None]:
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        tool_arg_buffers: dict[int, str] = {}
        usage_in = 0
        usage_out = 0

        for event in llm_anthropic.parse_stream_response(response, prompt_messages):
            kind = event.get("kind")
            if kind == "error":
                raise InvokeError(str(event.get("message") or "Anthropic stream error"))
            if kind == "usage":
                usage_in = int(event.get("input_tokens") or usage_in)
                usage_out = int(event.get("output_tokens") or usage_out)
            if kind == "text_delta":
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=event.get("text") or ""),
                    ),
                )
            elif kind == "tool_call_delta":
                idx = int(event.get("index") or 0)
                while len(tool_calls) <= idx:
                    tool_calls.append(
                        AssistantPromptMessage.ToolCall(
                            id="",
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name="", arguments=""
                            ),
                        )
                    )
                if event.get("id"):
                    tool_calls[idx].id = event["id"]
                if event.get("name"):
                    tool_calls[idx].function.name = event["name"]
                arg_delta = event.get("arguments_delta") or ""
                if arg_delta:
                    tool_arg_buffers[idx] = tool_arg_buffers.get(idx, "") + arg_delta
                    tool_calls[idx].function.arguments = tool_arg_buffers[idx]
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=idx,
                        message=AssistantPromptMessage(
                            content="",
                            tool_calls=[tool_calls[idx]],
                        ),
                    ),
                )
            elif kind == "stop":
                usage = None
                if usage_in or usage_out:
                    usage = self._calc_response_usage(
                        model, credentials, usage_in, usage_out
                    )
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=""),
                        finish_reason=(
                            "tool_calls"
                            if any(t.id or t.function.name for t in tool_calls)
                            else "stop"
                        ),
                        usage=usage,
                    ),
                )

    def _validate_anthropic_credentials(self, model: str, credentials: dict) -> None:
        body = {
            "model": credentials.get("endpoint_model_name") or model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "ping"}],
        }
        try:
            response = requests.post(
                self._anthropic_url(credentials),
                headers=self._anthropic_headers(credentials, credentials.get("extra_headers") or {}),
                json=body,
                timeout=(10, 60),
            )
        except requests.RequestException as ex:
            raise CredentialsValidateFailedError(
                f"OpenCode Anthropic Messages connection error: {ex}"
            ) from ex
        if response.status_code != 200:
            raise CredentialsValidateFailedError(
                f"Anthropic Messages validate failed ({response.status_code}): {response.text[:400]}"
            )

    # ------------------------------------------------------------------
    # OpenAI Responses
    # ------------------------------------------------------------------
    def _responses_headers(self, credentials: dict, headers: dict[str, str]) -> dict[str, str]:
        api_key = str(credentials.get("api_key") or "")
        return public_headers_for_protocol(headers, api_key, "responses")

    def _responses_url(self, credentials: dict) -> str:
        base = credentials.get("endpoint_url") or DEFAULT_ENDPOINT_URL
        return join_endpoint_url(base, "responses")

    def _build_responses_body(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        stream: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": credentials.get("endpoint_model_name") or model,
            "input": llm_responses.build_input_payload(prompt_messages),
            "stream": bool(stream),
            **llm_responses.filter_model_parameters(model_parameters),
        }
        tool_payload = llm_responses.build_tools_payload(tools)
        if tool_payload:
            body["tools"] = tool_payload
        return body

    def _invoke_responses(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        stop: Optional[list[str]],
        stream: bool,
        headers: dict[str, str],
    ):
        body = self._build_responses_body(
            model, credentials, prompt_messages, model_parameters, tools, stream
        )
        try:
            response = requests.post(
                self._responses_url(credentials),
                headers=self._responses_headers(credentials, headers),
                json=body,
                stream=stream,
                timeout=(10, 600),
            )
        except requests.RequestException as ex:
            raise InvokeError(f"OpenCode Responses connection error: {ex}") from ex

        if response.status_code != 200:
            raise llm_responses.map_http_error(response, response.text)

        if stream:
            return self._wrap_responses_stream(model, credentials, prompt_messages, response)

        data = response.json()
        text, tool_calls, in_tok, out_tok, status = llm_responses.parse_non_stream_response(data)
        assistant = AssistantPromptMessage(content=text, tool_calls=tool_calls or [])
        usage = self._calc_response_usage(model, credentials, in_tok, out_tok)
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant,
            usage=usage,
            system_fingerprint=data.get("id"),
        )

    def _wrap_responses_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        response: requests.Response,
    ) -> Generator[LLMResultChunk, None, None]:
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        tool_arg_buffers: dict[int, str] = {}
        usage_in = 0
        usage_out = 0

        for event in llm_responses.parse_stream_response(response):
            kind = event.get("kind")
            if kind == "error":
                raise InvokeError(str(event.get("message") or "Responses stream error"))
            if kind == "usage":
                usage_in = int(event.get("input_tokens") or usage_in)
                usage_out = int(event.get("output_tokens") or usage_out)
            if kind == "text_delta":
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=event.get("text") or ""),
                    ),
                )
            elif kind == "tool_call_delta":
                idx = int(event.get("index") or 0)
                while len(tool_calls) <= idx:
                    tool_calls.append(
                        AssistantPromptMessage.ToolCall(
                            id="",
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name="", arguments=""
                            ),
                        )
                    )
                if event.get("id"):
                    tool_calls[idx].id = event["id"]
                if event.get("name"):
                    tool_calls[idx].function.name = event["name"]
                arg_delta = event.get("arguments_delta") or ""
                if arg_delta:
                    tool_arg_buffers[idx] = tool_arg_buffers.get(idx, "") + arg_delta
                    tool_calls[idx].function.arguments = tool_arg_buffers[idx]
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=idx,
                        message=AssistantPromptMessage(
                            content="",
                            tool_calls=[tool_calls[idx]],
                        ),
                    ),
                )
            elif kind == "stop":
                usage = None
                if usage_in or usage_out:
                    usage = self._calc_response_usage(
                        model, credentials, usage_in, usage_out
                    )
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=""),
                        finish_reason=(
                            "tool_calls"
                            if any(t.id or t.function.name for t in tool_calls)
                            else "stop"
                        ),
                        usage=usage,
                    ),
                )

    def _validate_responses_credentials(self, model: str, credentials: dict) -> None:
        body = {
            "model": credentials.get("endpoint_model_name") or model,
            "input": [{"role": "user", "content": "ping"}],
            "max_output_tokens": 16,
        }
        try:
            response = requests.post(
                self._responses_url(credentials),
                headers=self._responses_headers(credentials, credentials.get("extra_headers") or {}),
                json=body,
                timeout=(10, 60),
            )
        except requests.RequestException as ex:
            raise CredentialsValidateFailedError(
                f"OpenCode Responses connection error: {ex}"
            ) from ex
        if response.status_code != 200:
            raise CredentialsValidateFailedError(
                f"Responses validate failed ({response.status_code}): {response.text[:400]}"
            )
