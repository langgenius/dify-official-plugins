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
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials) -> None:
        credentials["endpoint_url"] = str(
            URL(credentials.get("endpoint_url", "https://api.longcat.chat/openai"))
        )
        credentials["mode"] = LLMMode.CHAT.value
