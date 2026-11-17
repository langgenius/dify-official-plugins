"""OpenAI-compatible transport adapted from Dify SDK 0.10.2 for model-scoped timeouts.

Keep request construction aligned with the SDK when updating the dependency.
Response parsing and model features continue to use the SDK implementation.
"""

import json
import math
from collections.abc import Generator
from http import HTTPStatus
from typing import Any

import requests
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageFunction,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError
from dify_plugin.interfaces.model.openai_compatible.llm import (
    OAICompatLargeLanguageModel,
)
from pydantic import TypeAdapter


def request_timeout(credentials: dict) -> tuple[float, float]:
    value = credentials.get("request_timeout")
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        value = DifyPluginEnv().MAX_REQUEST_TIMEOUT
    try:
        if isinstance(value, bool):
            raise TypeError
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise InvokeBadRequestError(
            "Request read timeout must be a positive finite number of seconds"
        ) from None
    return (10, seconds)


class ConfigurableTimeoutLLM(OAICompatLargeLanguageModel):
    """Read the timeout from each call's credentials without changing shared SDK state."""

    def _request_credentials_validation(
        self, model: str, credentials: dict
    ) -> tuple[requests.Response, bool, LLMMode]:
        headers = {"Content-Type": "application/json"}
        extra_headers = credentials.get("extra_headers")
        if extra_headers is not None:
            headers = {**headers, **extra_headers}

        if api_key := credentials.get("api_key"):
            headers["Authorization"] = f"Bearer {api_key}"

        endpoint_url = credentials["endpoint_url"]
        validate_credentials_max_tokens = credentials.get("validate_credentials_max_tokens", 5) or 5
        data: dict[str, Any] = {
            "model": credentials.get("endpoint_model_name", model),
            "max_tokens": validate_credentials_max_tokens,
        }
        completion_type = LLMMode.value_of(credentials["mode"])

        if completion_type is LLMMode.CHAT:
            data["messages"] = [{"role": "user", "content": "ping"}]
            endpoint_url = self._join_endpoint_url(endpoint_url, "chat/completions")
        elif completion_type is LLMMode.COMPLETION:
            data["prompt"] = "ping"
            endpoint_url = self._join_endpoint_url(endpoint_url, "completions")
        else:
            msg = "Unsupported completion type for model configuration."
            raise ValueError(msg)

        stream_mode_auth = credentials.get("stream_mode_auth", "not_use")
        if stream_mode_auth == "use":
            stream_validate_max_tokens = credentials.get("validate_credentials_max_tokens") or 10
            data["max_tokens"] = stream_validate_max_tokens
            data["stream"] = True
            response = requests.post(
                endpoint_url,
                headers=headers,
                json=data,
                timeout=request_timeout(credentials),
                stream=True,
            )
            return response, True, completion_type

        response = requests.post(
            endpoint_url, headers=headers, json=data, timeout=request_timeout(credentials)
        )
        return response, False, completion_type

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
        """Invoke llm completion model

        :param model: model name
        :param credentials: credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result

        Returns:
            The return value.

        Raises:
            InvokeError: If model invocation fails.
            ValueError: If input values are invalid.
        """
        headers = {"Content-Type": "application/json", "Accept-Charset": "utf-8"}
        extra_headers = credentials.get("extra_headers")
        if extra_headers is not None:
            headers = {**headers, **extra_headers}

        api_key = credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        endpoint_url = credentials["endpoint_url"]

        response_format = model_parameters.get("response_format")
        if response_format:
            if response_format == "json_schema":
                json_schema = model_parameters.get("json_schema")
                if not json_schema:
                    msg = "Must define JSON Schema when the response format is " "json_schema"
                    raise ValueError(msg)
                try:
                    schema = TypeAdapter(dict[str, Any]).validate_json(json_schema)
                except Exception as exc:
                    msg = f"not correct json_schema format: {json_schema}"
                    raise ValueError(msg) from exc
                model_parameters.pop("json_schema")
                model_parameters["response_format"] = {"type": "json_schema", "json_schema": schema}
            else:
                model_parameters["response_format"] = {"type": response_format}
        elif "json_schema" in model_parameters:
            del model_parameters["json_schema"]

        data = {
            "model": credentials.get("endpoint_model_name", model),
            "stream": stream,
            **model_parameters,
        }

        completion_type = LLMMode.value_of(credentials["mode"])

        if completion_type is LLMMode.CHAT:
            endpoint_url = self._join_endpoint_url(endpoint_url, "chat/completions")
            data["messages"] = [
                self._convert_prompt_message_to_dict(m, credentials) for m in prompt_messages
            ]
        elif completion_type is LLMMode.COMPLETION:
            endpoint_url = self._join_endpoint_url(endpoint_url, "completions")
            data["prompt"] = prompt_messages[0].content
        else:
            msg = "Unsupported completion type for model configuration."
            raise ValueError(msg)

        # annotate tools with names, descriptions, etc.
        function_calling_type = credentials.get("function_calling_type", "no_call")
        formatted_tools = []
        if tools:
            if function_calling_type == "function_call":
                data["functions"] = [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.parameters,
                    }
                    for tool in tools
                ]
            elif function_calling_type == "tool_call":
                data["tool_choice"] = "auto"

                formatted_tools.extend(
                    PromptMessageFunction(function=tool).model_dump() for tool in tools
                )

                data["tools"] = formatted_tools

        if stop:
            data["stop"] = stop

        if user:
            data["user"] = user

        response = requests.post(
            endpoint_url,
            headers=headers,
            data=json.dumps(data, ensure_ascii=False, allow_nan=False).encode(
                "utf-8", "backslashreplace"
            ),
            timeout=request_timeout(credentials),
            stream=stream,
        )

        if response.encoding is None or response.encoding == "ISO-8859-1":
            response.encoding = "utf-8"

        if response.status_code != HTTPStatus.OK:
            msg = "API request failed with status code " f"{response.status_code}: {response.text}"
            raise InvokeError(msg)

        if stream:
            return self._handle_generate_stream_response(
                model, credentials, response, prompt_messages
            )

        return self._handle_generate_response(model, credentials, response, prompt_messages)
