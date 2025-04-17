import json
from collections.abc import Iterator
from typing import Any, Optional, Union
from dify_plugin.entities.model.message import PromptMessageTool
from requests import post
from models.llm.baichuan_turbo_errors import (
    BadRequestError,
    InsufficientAccountBalanceError,
    InternalServerError,
    InvalidAPIKeyError,
    InvalidAuthenticationError,
    RateLimitReachedError,
)


class BaichuanModel:
    api_key: str

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @property
    def _model_mapping(self) -> dict:
        return {
            "baichuan2-turbo": "Baichuan2-Turbo",
            "baichuan3-turbo": "Baichuan3-Turbo",
            "baichuan3-turbo-128k": "Baichuan3-Turbo-128k",
            "baichuan4": "Baichuan4",
            "baichuan4-turbo": "Baichuan4-Turbo",
            "baichuan4-air": "Baichuan4-Air",
        }

    @property
    def request_headers(self) -> dict[str, Any]:
        return {"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key}

    def _build_parameters(
        self,
        model: str,
        stream: bool,
        messages: list[dict],
        parameters: dict[str, Any],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> dict[str, Any]:
        if model in self._model_mapping:
            if parameters.get("res_format") == "json_object":
                parameters["response_format"] = {"type": "json_object"}
            if tools or parameters.get("with_search_enhance") is True:
                parameters["tools"] = []
            if parameters.get("with_search_enhance") is True:
                parameters["tools"].append({"type": "web_search", "web_search": {"enable": True}})
            if tools:
                for tool in tools:
                    parameters["tools"].append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.parameters,
                            },
                        }
                    )
            return {"model": self._model_mapping.get(model), "stream": stream, "messages": messages, **parameters}
        else:
            raise BadRequestError(f"Unknown model: {model}")

    def generate(
        self,
        model: str,
        stream: bool,
        messages: list[dict],
        parameters: dict[str, Any],
        timeout: int,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> Union[Iterator, dict]:
        if model in self._model_mapping:
            api_base = "https://api.baichuan-ai.com/v1/chat/completions"
        else:
            raise BadRequestError(f"Unknown model: {model}")
        data = self._build_parameters(model, stream, messages, parameters, tools)
        try:
            response = post(
                url=api_base, headers=self.request_headers, data=json.dumps(data), timeout=timeout, stream=stream
            )
        except Exception as e:
            raise InternalServerError(f"Failed to invoke model: {e}")
        if response.status_code != 200:
            try:
                resp = response.json()
                err = resp["error"]["type"]
                msg = resp["error"]["message"]
            except Exception as e:
                raise InternalServerError(f"Failed to convert response to json: {e} with text: {response.text}")
            if err == "invalid_api_key":
                raise InvalidAPIKeyError(msg)
            elif err == "insufficient_quota":
                raise InsufficientAccountBalanceError(msg)
            elif err == "invalid_authentication":
                raise InvalidAuthenticationError(msg)
            elif err == "invalid_request_error":
                raise BadRequestError(msg)
            elif "rate" in err:
                raise RateLimitReachedError(msg)
            elif "internal" in err:
                raise InternalServerError(msg)
            elif err == "api_key_empty":
                raise InvalidAPIKeyError(msg)
            else:
                raise InternalServerError(f"Unknown error: {err} with message: {msg}")
        if stream:
            return response.iter_lines()
        else:
            return response.json()
