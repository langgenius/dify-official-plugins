from collections.abc import Generator
from typing import Optional, Union
import logging
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

from ._metadata import apply_dify_headers_if_enabled

logger = logging.getLogger(__name__)


class NVIDIANIMProvider(OAICompatLargeLanguageModel):
    """
    Model class for NVIDIA NIM large language model.
    """

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
        # Run the opt-in helper so any caller-supplied ``extra_headers``
        # (or the Dify default headers when ``enable_request_metadata``
        # is ``"enabled"``) are written into
        # ``credentials['extra_headers']`` before the OAICompat base
        # class builds the OpenAI client. The OAICompat base class
        # forwards ``extra_headers`` as ``default_headers=`` on the
        # OpenAI client constructor, which the OpenAI SDK sends on
        # every outbound request.
        apply_dify_headers_if_enabled(credentials)
        return super()._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        apply_dify_headers_if_enabled(credentials)
        super().validate_credentials(model, credentials)
