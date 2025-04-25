from collections.abc import Generator
from typing import Optional, Union

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool


class GiteeAILargeLanguageModel(OAICompatLargeLanguageModel):

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
        self._add_custom_parameters(credentials, model, model_parameters, stream)
        return super()._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials, model, None, True)
        super().validate_credentials(model, credentials)

    def _add_custom_parameters(self, credentials: dict, model: str, model_parameters: dict, stream: bool) -> None:
        credentials["endpoint_url"] = "https://ai.gitee.com/v1"
        credentials["mode"] = LLMMode.CHAT.value
        if model_parameters is not None:
            model_parameters["stream"] = stream

        schema = self.get_model_schema(model, credentials)
        assert schema is not None, f"Model schema not found for model {model}"
        assert schema.features is not None, f"Model features not found for model {model}"
        if ModelFeature.TOOL_CALL in schema.features or ModelFeature.MULTI_TOOL_CALL in schema.features or ModelFeature.STREAM_TOOL_CALL in schema.features:
            credentials["function_calling_type"] = "tool_call"
