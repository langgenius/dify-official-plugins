import json
import logging
from collections.abc import Generator
from html import escape

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from requests import Response

logger = logging.getLogger(__name__)

PLUGIN_VERSION = "0.0.1"
DEFAULT_BASE_URL = "https://api.sarvam.ai/v2"
USER_AGENT = f"dify-sarvam-plugin/{PLUGIN_VERSION}"
_THINK_OPEN = "<think>\n"
_THINK_CLOSE = "\n</think>"


class SarvamLargeLanguageModel(OAICompatLargeLanguageModel):
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
        self._prepare_credentials(credentials)
        return super()._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._prepare_credentials(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _prepare_credentials(credentials: dict) -> None:
        endpoint_url = (credentials.get("endpoint_url") or "").strip()
        credentials["endpoint_url"] = endpoint_url or DEFAULT_BASE_URL
        credentials["mode"] = "chat"
        credentials["function_calling_type"] = "tool_call"
        credentials["stream_function_calling"] = "supported"
        # Reasoning tokens count against max_tokens, so a tiny validation
        # budget can produce an empty answer on sarvam-105b.
        credentials["validate_credentials_max_tokens"] = 64

        headers = credentials.get("extra_headers") or {}
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except json.JSONDecodeError:
                headers = {}
        if not isinstance(headers, dict):
            headers = {}
        headers["User-Agent"] = USER_AGENT
        credentials["extra_headers"] = headers

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        result = super()._handle_generate_response(
            model=model,
            credentials=credentials,
            response=response,
            prompt_messages=prompt_messages,
        )
        message = response.json()["choices"][0].get("message", {})
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning:
            return result

        result.message.opaque_body = {
            **(result.message.opaque_body or {}),
            "reasoning_content": reasoning,
        }
        result.message.content = (
            f"{_THINK_OPEN}{escape(reasoning, quote=False)}{_THINK_CLOSE}"
            f"{result.message.content or ''}"
        )
        return result

    def _convert_prompt_message_to_dict(
        self,
        message: PromptMessage,
        credentials: dict | None = None,
    ) -> dict:
        message_dict = super()._convert_prompt_message_to_dict(message, credentials)
        if not isinstance(message, AssistantPromptMessage):
            return message_dict
        content = message.content
        if not isinstance(content, str) or not content.startswith(_THINK_OPEN):
            return message_dict
        end = content.find(_THINK_CLOSE)
        if end == -1:
            return message_dict
        message_dict["content"] = content[end + len(_THINK_CLOSE) :]
        return message_dict
