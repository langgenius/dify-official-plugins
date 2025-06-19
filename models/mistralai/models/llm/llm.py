from collections.abc import Generator
from typing import Optional, Union
import logging
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

logger = logging.getLogger(__name__)


class MistralAILargeLanguageModel(OAICompatLargeLanguageModel):
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

        # Transform reasoning_mode to prompt_mode for Magistral models
        if "magistral" in model.lower() and "reasoning_mode" in model_parameters:
            reasoning_enabled = model_parameters.pop("reasoning_mode")
            if reasoning_enabled:
                model_parameters["prompt_mode"] = "reasoning"
            else:
                model_parameters["prompt_mode"] = None

        stop = []
        user = None
        return super()._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        credentials["mode"] = "chat"
        credentials["endpoint_url"] = "https://api.mistral.ai/v1"






