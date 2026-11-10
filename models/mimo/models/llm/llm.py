from collections.abc import Generator
from typing import Optional, Union
import requests
from dify_plugin.entities.model.llm import LLMResult, LLMMode
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin import OAICompatLargeLanguageModel

from models.llm._metadata import apply_dify_headers_if_enabled


class MimoLargeLanguageModel(OAICompatLargeLanguageModel):
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
        apply_dify_headers_if_enabled(credentials)
        thinking_type = model_parameters.pop("thinking", "disabled")
        model_parameters["thinking"] = {"type": thinking_type}
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        apply_dify_headers_if_enabled(credentials)
        super().validate_credentials(model, credentials)

    def _request_credentials_validation(
        self, model: str, credentials: dict
    ) -> tuple[requests.Response, bool, LLMMode]:
        # MiMo uses max_completion_tokens and enables thinking by default.
        # Keep the connection check short with an explicit non-thinking request.
        response = requests.post(
            self._join_endpoint_url(credentials["endpoint_url"], "chat/completions"),
            headers={
                "Content-Type": "application/json",
                **(credentials.get("extra_headers") or {}),
                "Authorization": f"Bearer {credentials['api_key']}",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_completion_tokens": 5,
                "thinking": {"type": "disabled"},
            },
            timeout=(10, 300),
        )
        return response, False, LLMMode.CHAT

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        if not credentials.get("endpoint_url"):
            credentials["endpoint_url"] = "https://api.xiaomimimo.com/v1"
        credentials["mode"] = LLMMode.CHAT.value
        credentials["function_calling_type"] = "tool_call"
