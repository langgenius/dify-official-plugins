from collections.abc import Generator
from typing import Optional, Union
from dify_plugin.entities.model.llm import LLMResult, LLMMode
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin import OAICompatLargeLanguageModel
from yarl import URL


class LongCatLargeLanguageModel(OAICompatLargeLanguageModel):
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
        if model == "LongCat-2.0" and "enable_thinking" in model_parameters:
            enable_thinking = model_parameters.pop("enable_thinking")
            model_parameters["thinking"] = {
                "type": "enabled" if enable_thinking else "disabled"
            }
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials) -> None:
        credentials["endpoint_url"] = str(
            URL(credentials.get("endpoint_url") or "https://api.longcat.chat/openai/v1")
        )
        credentials["mode"] = LLMMode.CHAT.value
        credentials["function_calling_type"] = "tool_call"
        credentials["stream_function_calling"] = "supported"
