import json
import re
from contextlib import suppress
from typing import Generator, List, Mapping, Optional, Union
import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from dify_plugin.entities.model import (
    AIModelEntity,
    I18nObject,
    ModelFeature,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

_VALIDATE_TIMEOUT = (10, 60)
_DEFAULT_BASE_URL = "http://127.0.0.1:1337/v1"


def _normalize_base_url(endpoint_url: str) -> str:
    return endpoint_url.rstrip("/")


def _build_headers(credentials: dict) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = credentials.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def validate_atomic_chat_credentials(credentials: dict, model: str | None = None) -> None:
    if not model:
        raise CredentialsValidateFailedError("Please specify a model name")

    endpoint_url = credentials.get("endpoint_url") or _DEFAULT_BASE_URL
    base_url = _normalize_base_url(endpoint_url)
    models_url = f"{base_url}/models"
    headers = _build_headers(credentials)

    try:
        response = requests.get(models_url, headers=headers, timeout=_VALIDATE_TIMEOUT)
    except (ConnectionError, Timeout, RequestException) as ex:
        raise CredentialsValidateFailedError(
            f"Cannot connect to Atomic Chat at {base_url}. "
            "Enable Settings → Local API Server in Atomic Chat and try again."
        ) from ex

    if response.status_code != 200:
        raise CredentialsValidateFailedError(
            f"Credentials validation failed with status code {response.status_code} when checking {models_url}"
        )

    try:
        models_result = response.json()
    except json.JSONDecodeError as ex:
        raise CredentialsValidateFailedError("Failed to parse models response: JSON decode error") from ex

    if "data" not in models_result:
        raise CredentialsValidateFailedError("Invalid models response format: missing 'data' field")

    available_models = [
        model_info["id"]
        for model_info in models_result.get("data", [])
        if isinstance(model_info, dict) and "id" in model_info
    ]

    if model not in available_models:
        raise CredentialsValidateFailedError(
            f"Model '{model}' is not available on Atomic Chat. "
            f"Download a model in Atomic Chat first. Available: {', '.join(available_models) or 'none'}"
        )


class AtomicChatLargeLanguageModel(OAICompatLargeLanguageModel):
    _THINK_PATTERN = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

    def get_customizable_model_schema(self, model: str, credentials: Mapping | dict) -> AIModelEntity:
        customized_credentials = dict(credentials)
        self._add_custom_parameters(customized_credentials)
        entity = super().get_customizable_model_schema(model, customized_credentials)

        if credentials.get("agent_thought_support", "supported") == "supported":
            if ModelFeature.AGENT_THOUGHT not in entity.features:
                entity.features.append(ModelFeature.AGENT_THOUGHT)

        entity.parameter_rules.append(
            ParameterRule(
                name="enable_thinking",
                label=I18nObject(en_us="Thinking mode", zh_hans="思考模式"),
                help=I18nObject(
                    en_us="Enable chain-of-thought style output for supported local models.",
                    zh_hans="为支持的本地模型启用思考模式输出。",
                ),
                type=ParameterType.BOOLEAN,
                required=False,
            )
        )
        return entity

    @classmethod
    def _drop_analyze_channel(cls, prompt_messages: List[PromptMessage]) -> None:
        for message in prompt_messages:
            if not isinstance(message, AssistantPromptMessage):
                continue
            if not isinstance(message.content, str) or "<think>" not in message.content:
                continue
            message.content = cls._THINK_PATTERN.sub("", message.content)

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
        self._add_custom_parameters(credentials)

        if model_parameters.get("response_format") == "json_schema":
            json_schema_str = model_parameters.get("json_schema")
            if json_schema_str:
                structured_output_prompt = (
                    "Your response must be a JSON object that validates against the following JSON schema, "
                    f"and nothing else.\nJSON Schema: ```json\n{json_schema_str}\n```"
                )
                existing_system_prompt = next(
                    (message for message in prompt_messages if message.role == PromptMessageRole.SYSTEM),
                    None,
                )
                if existing_system_prompt:
                    existing_system_prompt.content = (
                        f"{structured_output_prompt}\n\n{existing_system_prompt.content}"
                    )
                else:
                    prompt_messages.insert(0, SystemPromptMessage(content=structured_output_prompt))

        enable_thinking = model_parameters.pop("enable_thinking", None)
        if enable_thinking is not None:
            model_parameters["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}

        with suppress(Exception):
            self._drop_analyze_channel(prompt_messages)

        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        endpoint_url = credentials.get("endpoint_url") or _DEFAULT_BASE_URL
        credentials["endpoint_url"] = _normalize_base_url(endpoint_url)
        credentials.setdefault("mode", "chat")
        credentials.setdefault("function_calling_type", "tool_call")
        credentials.setdefault("stream_function_calling", "supported")
        credentials.setdefault("max_tokens_to_sample", 4096)
        credentials.setdefault("stream_mode_delimiter", "\n\n")
        credentials.setdefault("stream_mode_auth", "not_use")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        validate_atomic_chat_credentials(credentials, model)
