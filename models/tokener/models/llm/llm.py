from collections.abc import Generator

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageFunction,
    PromptMessageTool,
)

from models._credentials import ENDPOINT_URL, validate_model_access


class TokenerLargeLanguageModel(OAICompatLargeLanguageModel):
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

    def _validate_and_filter_model_parameters(
        self, model: str, model_parameters: dict, credentials: dict
    ) -> dict:
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
        return super().get_num_tokens(
            model,
            self._model_credentials(model, credentials),
            prompt_messages,
            tools,
        )

    def _model_credentials(self, model: str, credentials: dict) -> dict:
        resolved = {**credentials, "endpoint_url": ENDPOINT_URL, "mode": "chat"}
        schema = self.get_model_schema(model)
        if schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL} & set(
            schema.features or []
        ):
            resolved["function_calling_type"] = "tool_call"
        return resolved
