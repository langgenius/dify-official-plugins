import json
import math
import uuid
from collections.abc import Generator, Mapping
from pathlib import Path

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    PromptMessage,
    PromptMessageFunction,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError

from models._api import TokenerAPIModel, redirect_family
from models._credentials import ENDPOINT_URL, validate_model_access
from models.llm import (
    _anthropic_format,
    _anthropic_messages,
    _chat_compat,
    _gemini_native,
    _openai_decisions,
    _openai_responses,
    _wire,
)
from models.llm._tool_stream import (
    _has_complete_arguments as _has_complete_arguments,
)
from models.llm._tool_stream import _ToolCallStreamResponse as _ToolCallStreamResponse

CHAT_FIELDS = {
    "audio": _chat_compat.AUDIO_FIELDS,
    "tongyi": _chat_compat.TONGYI_FIELDS,
    "xai": _chat_compat.XAI_FIELDS,
}
NATIVE_FIELDS = {
    "openai": _openai_responses.FIELDS | {"seed"},
    "anthropic": _anthropic_messages.FIELDS,
    "gemini": _gemini_native.FIELDS,
}
SOURCE_MODEL_PROVIDERS = json.loads(Path(__file__).with_name("_provider_models.json").read_text())


def model_family(model: str) -> str:
    base = _openai_responses.base_model(model)
    if base.startswith("gpt-audio"):
        return "audio"
    if model in SOURCE_MODEL_PROVIDERS:
        return SOURCE_MODEL_PROVIDERS[model]
    if family := redirect_family(model):
        return family
    if (
        base.startswith(("gpt-3.5", "gpt-4", "gpt-5", "gpt-6", "chatgpt-4o-"))
        or base in {"chat-latest", "babbage-002", "davinci-002"}
        or (len(base) > 1 and base[0] == "o" and base[1].isdigit())
    ):
        return "openai"
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith(("gemini-", "learnlm-", "gemma-")):
        return "gemini"
    if model.startswith(("qwen", "qwq-", "qvq-")):
        return "tongyi"
    if model.startswith("grok-"):
        return "xai"
    return ""


def _uses_openai_chat(model: str, parameters: dict, prompt_messages: list[PromptMessage]) -> bool:
    base = _openai_responses.base_model(model)
    if base.startswith(_openai_responses.RESPONSES_ONLY_PREFIXES):
        return False
    if parameters.get("seed") is not None:
        return True
    if any(
        parameters.get(name) not in (None, 0, 0.0)
        for name in ("frequency_penalty", "presence_penalty")
    ):
        return True
    return any(
        isinstance(item, AudioPromptMessageContent)
        for message in prompt_messages
        if isinstance(message.content, list)
        for item in message.content
    )


class TokenerLargeLanguageModel(OAICompatLargeLanguageModel, TokenerAPIModel):
    def get_customizable_model_schema(
        self, model: str, credentials: Mapping
    ) -> AIModelEntity | None:
        return TokenerAPIModel.get_customizable_model_schema(self, model, credentials)

    def _code_block_mode_wrapper(
        self,
        model,
        credentials,
        prompt_messages,
        model_parameters,
        tools=None,
        stop=None,
        stream=True,
        user=None,
    ):
        if model_family(model) != "anthropic":
            return super()._code_block_mode_wrapper(
                model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
            )
        return _anthropic_format.code_block_mode(
            self,
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
            model.startswith(_anthropic_messages.NO_PREFILL),
        )

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
        family = model_family(model)
        model_parameters = _wire.reject_top_parameters(family, model_parameters)
        if model == _openai_decisions.MODEL:
            return _openai_decisions.generate(
                self,
                model,
                credentials,
                prompt_messages,
                model_parameters,
                tools,
                stop,
                user,
            )
        if family:
            parameters = model_parameters.copy()
            if "_native_response_format" in parameters:
                parameters["response_format"] = parameters.pop("_native_response_format")
            if family == "openai":
                if _uses_openai_chat(model, parameters, prompt_messages):
                    return _chat_compat.invoke(
                        self,
                        "openai",
                        model,
                        credentials,
                        prompt_messages,
                        parameters,
                        tools,
                        stop,
                        stream,
                        user,
                    )
                return _openai_responses.invoke(
                    self,
                    model,
                    credentials,
                    prompt_messages,
                    parameters,
                    tools,
                    stop,
                    stream,
                    user,
                )
            if family == "anthropic":
                return _anthropic_messages.invoke(
                    self,
                    model,
                    credentials,
                    prompt_messages,
                    parameters,
                    tools,
                    stop,
                    stream,
                )
            if family == "gemini":
                return _gemini_native.invoke(
                    self,
                    model,
                    credentials,
                    prompt_messages,
                    parameters,
                    tools,
                    stop,
                    stream,
                )
            return _chat_compat.invoke(
                self,
                family,
                model,
                credentials,
                prompt_messages,
                parameters,
                tools,
                stop,
                stream,
                user,
            )
        return super()._invoke(
            model=model,
            credentials=self._model_credentials(model, credentials),
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        if credentials.get("function_calling_type") != "tool_call":
            yield from super()._handle_generate_stream_response(
                model, credentials, response, prompt_messages
            )
            return
        adapted = _ToolCallStreamResponse(response)
        for chunk in super()._handle_generate_stream_response(
            model, credentials, adapted, prompt_messages
        ):
            if adapted.tool_calls and chunk.delta.usage is not None:
                calls = [
                    call
                    for call in adapted.tool_calls
                    if call.function.name or call.function.arguments
                ]
                for call in calls:
                    if not call.id:
                        call.id = f"chatcmpl-tool-{uuid.uuid4().hex}"
                if calls:
                    yield LLMResultChunk(
                        model=model,
                        delta=LLMResultChunkDelta(
                            index=chunk.delta.index,
                            message=AssistantPromptMessage(content="", tool_calls=calls),
                        ),
                    )
                adapted.tool_calls.clear()
                adapted.indexed_calls.clear()
            yield chunk

    def _validate_and_filter_model_parameters(
        self, model: str, model_parameters: dict, credentials: dict
    ) -> dict:
        family = model_family(model)
        model_parameters = _wire.reject_top_parameters(family, model_parameters)
        if model == _openai_decisions.MODEL:
            return {}
        if family:
            model_parameters = model_parameters.copy()
            for name, value in model_parameters.items():
                if name not in {"response_format", "json_schema"}:
                    _wire.reject_controls(value)
            if family == "tongyi":
                _chat_compat.normalize_deepseek_parameters(model, model_parameters)
            aliases = {
                "openai": ("max_output_tokens", "max_tokens", "max_completion_tokens"),
                "anthropic": ("max_tokens_to_sample", "max_tokens"),
                "gemini": ("max_output_tokens", "max_tokens_to_sample", "max_tokens"),
                "tongyi": ("max_completion_tokens", "max_tokens"),
            }.get(family, ())
            rules = self.get_parameter_rules(model, credentials)
            if family == "anthropic":
                rule_names = {rule.name for rule in rules}
                for name in ("prompt_caching_ttl", "task_budget", "speed"):
                    if name not in rule_names:
                        model_parameters.pop(name, None)
            target = next((rule.name for rule in rules if rule.name in aliases), None)
            if target:
                supplied = next(
                    (
                        model_parameters[name]
                        for name in aliases
                        if model_parameters.get(name) is not None
                    ),
                    None,
                )
                if supplied is not None:
                    for name in aliases:
                        model_parameters.pop(name, None)
                    model_parameters[target] = supplied
            validated = super()._validate_and_filter_model_parameters(
                model,
                {
                    name: value
                    for name, value in model_parameters.items()
                    if name not in {"response_format", "json_schema"}
                },
                credentials,
            )
            model_parameters = {**model_parameters, **validated}
            allowed = NATIVE_FIELDS.get(family) or CHAT_FIELDS[family]
            parameters = {
                name: value
                for name, value in model_parameters.items()
                if name in allowed and value is not None
            }
            for name, value in parameters.items():
                if name not in {"response_format", "json_schema"}:
                    _wire.reject_controls(value)
            for name in (
                "temperature",
                "top_p",
                "top_k",
                "presence_penalty",
                "frequency_penalty",
                "seed",
                "thinking_budget",
                "task_budget",
                "max_tokens",
                "max_output_tokens",
                "max_completion_tokens",
            ):
                if name in parameters and (
                    type(parameters[name]) not in (int, float)
                    or not math.isfinite(parameters[name])
                ):
                    raise InvokeBadRequestError(f"Invalid numeric parameter: {name}")
            if (effort := parameters.get("reasoning_effort")) is not None and (
                not isinstance(effort, str) or not effort
            ):
                raise InvokeBadRequestError("reasoning_effort must be a non-empty string")
            if family == "openai" and effort not in (
                None,
                "none",
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            ):
                raise InvokeBadRequestError("Invalid reasoning_effort")
            if (
                family == "openai"
                and "seed" in parameters
                and _openai_responses.base_model(model).startswith(
                    _openai_responses.RESPONSES_ONLY_PREFIXES
                )
            ):
                raise InvokeBadRequestError("seed requires Chat Completions")
            for name in (
                "enable_stream",
                "enable_thinking",
                "enable_search",
                "incremental_output",
                "include_thoughts",
                "use_inline_file",
                "grounding",
                "code_execution",
                "url_context",
            ):
                if name in parameters and type(parameters[name]) is not bool:
                    raise InvokeBadRequestError(f"{name} must be a boolean")
            if "response_format" in parameters:
                value = parameters["response_format"]
                if family == "gemini" and isinstance(value, str) and value.lower() == "xml":
                    parameters.pop("response_format")
                elif isinstance(value, str) and (
                    value.lower() == "xml" or (family == "anthropic" and value == "JSON")
                ):
                    parameters["response_format"] = value.upper()
                else:
                    parameters["_native_response_format"] = parameters.pop("response_format")
            return parameters
        rules = self.get_parameter_rules(model, credentials)
        declared = {rule.name for rule in rules} | {
            rule.use_template for rule in rules if rule.use_template
        }
        for name, value in model_parameters.items():
            if name in declared and name in {
                "temperature",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "seed",
            }:
                if isinstance(value, bool) or (
                    isinstance(value, float) and not math.isfinite(value)
                ):
                    raise ValueError(f"Invalid numeric parameter: {name}")
        filtered = super()._validate_and_filter_model_parameters(
            model, model_parameters, credentials
        )
        if model_parameters.get("tool_choice") is not None:
            filtered["tool_choice"] = model_parameters["tool_choice"]
        return filtered

    def _generate(
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
        if (
            tools
            and model_parameters.get("tool_choice") is not None
            and credentials.get("function_calling_type") == "tool_call"
        ):
            model_parameters = {
                **model_parameters,
                "tools": [PromptMessageFunction(function=tool).model_dump() for tool in tools],
            }
            tools = None
        else:
            model_parameters = {
                key: value for key, value in model_parameters.items() if key != "tool_choice"
            }
        return super()._generate(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        validate_model_access(credentials, model)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        family = model_family(model)
        if family == "anthropic":
            count = _anthropic_messages.count_tokens(
                self, model, credentials, prompt_messages, tools
            )
            if count is not None:
                return count
        if family == "gemini":
            return self._get_num_tokens_by_gpt2(_gemini_native.prompt_text(prompt_messages))
        if family in ("anthropic", "openai"):
            return _openai_responses.count_messages(model, prompt_messages, tools)
        return super().get_num_tokens(
            model,
            self._model_credentials(model, credentials),
            prompt_messages,
            tools,
        )

    def _model_credentials(self, model: str, credentials: dict) -> dict:
        resolved = {"api_key": credentials["api_key"], "endpoint_url": ENDPOINT_URL, "mode": "chat"}
        schema = self.get_model_schema(model, credentials)
        if schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL} & set(
            schema.features or []
        ):
            resolved["function_calling_type"] = "tool_call"
        return resolved
