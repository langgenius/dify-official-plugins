"""OpenCode Go LLM provider — single entry that routes chat / Anthropic / Responses.

dify_plugin registers one LargeLanguageModel class per ModelType (last source
wins), so protocol selection must live inside this class rather than three
model_sources.
"""

from __future__ import annotations

import time
from collections.abc import Generator
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
        add_custom_parameters,
        extra_headers_rule,
        join_endpoint_url,
        public_headers_for_protocol,
        resolve_protocol,
    )
except ImportError:  # pragma: no cover - importlib standalone load
    import llm_anthropic
    import llm_responses
    import session_headers
    from session_headers import (
        DEFAULT_ENDPOINT_URL,
        add_custom_parameters,
        extra_headers_rule,
        join_endpoint_url,
        public_headers_for_protocol,
        resolve_protocol,
    )

# Back-compat aliases (tests and older imports).
_extra_headers_rule = extra_headers_rule


# OpenCode Go gateway hard-pins sampling params for some models.
# Overrides survive stale Dify UI defaults after schema updates.
MODEL_PARAMETER_OVERRIDES: dict[str, dict[str, Any]] = {
    "kimi-k2.7-code": {"temperature": 1.0, "top_p": 0.95},
}

# Parameters these models reject entirely (400 Unsupported parameter).
MODEL_PARAMETER_STRIP: dict[str, frozenset[str]] = {
    "gpt-5.6-luna": frozenset({"temperature", "top_p"}),
}

# union-alpha SSE frequently 503s / returns empty bodies while non-stream is
# stable. Dify still asks for a generator, so we emulate one chunk.
FORCE_NONSTREAM_MODELS = frozenset({"union-alpha"})


def apply_model_parameter_constraints(model: str, model_parameters: dict) -> dict:
    updated = dict(model_parameters)
    for key in MODEL_PARAMETER_STRIP.get(model, ()):
        updated.pop(key, None)
    overrides = MODEL_PARAMETER_OVERRIDES.get(model)
    if overrides:
        updated.update(overrides)
    return updated


_RETRYABLE_STATUS = {502, 503, 529}


def _post_with_retry(
    url: str,
    headers: dict,
    body: dict,
    stream: bool,
    *,
    attempts: int = 4,
    backoff: float = 1.2,
) -> requests.Response:
    """POST with retries on transient upstream unavailability.

    OpenCode free models (especially union-alpha) 503 intermittently even when
    healthy — a few short retries hide most of that from Dify workflows.
    """
    session = requests.Session()
    # Honor HTTP(S)_PROXY / system proxy. Responses-line models (grok / gpt-luna
    # / muse) are region-restricted and usually need an outbound proxy from CN.
    session.trust_env = True
    last: Optional[requests.Response] = None
    attempts = max(1, attempts)
    for attempt in range(attempts):
        response = session.post(
            url,
            headers=headers,
            json=body,
            stream=stream,
            timeout=(10, 600),
        )
        last = response
        if response.status_code not in _RETRYABLE_STATUS or attempt == attempts - 1:
            return response
        # Drain connection body so the socket can be reused.
        try:
            response.close()
        except Exception:
            pass
        time.sleep(backoff * (attempt + 1))
    assert last is not None
    return last


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
        return session_headers.parse_extra_headers(raw)

    @classmethod
    def _apply_extra_headers(cls, credentials: dict, model_parameters: dict) -> None:
        session_headers.apply_extra_headers(credentials, model_parameters)

    @classmethod
    def _current_conversation_id(cls) -> Optional[str]:
        return session_headers.current_conversation_id()

    @classmethod
    def _current_rpc_session_id(cls) -> Optional[str]:
        return session_headers.current_rpc_session_id()

    @staticmethod
    def _is_resolved_id(value: str) -> bool:
        return session_headers.is_resolved_id(value)

    @classmethod
    def _build_session_id(cls, user: Optional[str], credentials: dict) -> str:
        return session_headers.build_session_id(user, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict, user: Optional[str]) -> None:
        session_headers.add_custom_parameters(credentials, user)

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
        model_parameters = apply_model_parameter_constraints(model, model_parameters)
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
        force_nonstream = model in FORCE_NONSTREAM_MODELS
        use_stream = bool(stream) and not force_nonstream
        body = self._build_anthropic_body(
            model, credentials, prompt_messages, model_parameters, tools, use_stream
        )
        if stop:
            body["stop_sequences"] = list(stop)
        try:
            response = _post_with_retry(
                self._anthropic_url(credentials),
                self._anthropic_headers(credentials, headers),
                body,
                use_stream,
                attempts=5 if force_nonstream else 4,
            )
        except requests.RequestException as ex:
            raise InvokeError(
                f"OpenCode Anthropic Messages connection error: {ex}"
            ) from ex

        if response.status_code != 200:
            raise llm_anthropic.map_http_error(response, response.text)

        # OpenCode often omits charset; requests then defaults to ISO-8859-1 and
        # corrupts Chinese text in stream/json decoding.
        if not response.encoding or response.encoding.lower() in {
            "iso-8859-1",
            "latin-1",
        }:
            response.encoding = "utf-8"

        if use_stream:
            return self._wrap_anthropic_stream(model, credentials, prompt_messages, response)

        data = response.json()
        text, tool_calls, in_tok, out_tok, stop_reason = (
            llm_anthropic.parse_non_stream_response(data)
        )
        assistant = AssistantPromptMessage(content=text, tool_calls=tool_calls or [])
        usage = self._calc_response_usage(model, credentials, in_tok, out_tok)
        result = LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant,
            usage=usage,
            system_fingerprint=None,
        )
        if stream:
            # Dify asked for a stream; emulate a single-chunk generator.
            return self._result_as_stream(result)
        return result

    def _result_as_stream(self, result: LLMResult) -> Generator[LLMResultChunk, None, None]:
        yield LLMResultChunk(
            model=result.model,
            prompt_messages=result.prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=result.message,
                finish_reason="stop",
                usage=result.usage,
            ),
        )

    def _emit_stream_events(
        self,
        events,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        error_label: str,
    ) -> Generator[LLMResultChunk, None, None]:
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        tool_arg_buffers: dict[int, str] = {}
        usage_in = 0
        usage_out = 0
        finished = False

        for event in events:
            kind = event.get("kind")
            if kind == "error":
                raise InvokeError(str(event.get("message") or f"{error_label} stream error"))
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
                if finished:
                    continue
                finished = True
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

    def _wrap_anthropic_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        response: requests.Response,
    ) -> Generator[LLMResultChunk, None, None]:
        yield from self._emit_stream_events(
            llm_anthropic.parse_stream_response(response, prompt_messages),
            model,
            credentials,
            prompt_messages,
            "Anthropic",
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
        if stop:
            # OpenAI Responses text config; accepted by OpenCode /responses gateways.
            text_cfg = dict(body.get("text") or {})
            text_cfg["stop"] = list(stop)
            body["text"] = text_cfg
        try:
            response = _post_with_retry(
                self._responses_url(credentials),
                self._responses_headers(credentials, headers),
                body,
                stream,
            )
        except requests.RequestException as ex:
            raise InvokeError(f"OpenCode Responses connection error: {ex}") from ex

        if response.status_code != 200:
            raise llm_responses.map_http_error(response, response.text)

        if not response.encoding or response.encoding.lower() in {
            "iso-8859-1",
            "latin-1",
        }:
            response.encoding = "utf-8"

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
            system_fingerprint=None,
        )

    def _wrap_responses_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        response: requests.Response,
    ) -> Generator[LLMResultChunk, None, None]:
        yield from self._emit_stream_events(
            llm_responses.parse_stream_response(response),
            model,
            credentials,
            prompt_messages,
            "Responses",
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
