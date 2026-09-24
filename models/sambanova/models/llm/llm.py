from collections.abc import Generator
from typing import Optional, Union
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

from ._metadata import apply_dify_headers_if_enabled


class SambaNovaLargeLanguageModel(OAICompatLargeLanguageModel):
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
        # Run the opt-in helper so any caller-supplied ``extra_headers``
        # (or the Dify default headers when ``enable_request_metadata``
        # is ``"enabled"``) are written into
        # ``credentials['extra_headers']`` before the OAICompat base
        # class builds the OpenAI client. The OAICompat base class
        # forwards ``extra_headers`` as ``default_headers=`` on the
        # OpenAI client constructor, which the OpenAI SDK sends on
        # every outbound request.
        apply_dify_headers_if_enabled(credentials)
        return super()._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        apply_dify_headers_if_enabled(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        credentials["mode"] = "chat"
        credentials["endpoint_url"] = "https://api.sambanova.ai/v1"
