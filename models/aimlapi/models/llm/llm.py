from collections.abc import Generator
from typing import Optional, Union

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    UserPromptMessage,
)


class AimlapiLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = "https://api.aimlapi.com/v1"
        credentials["mode"] = self.get_model_mode(model).value
        credentials["openai_api_key"] = credentials.get("api_key")
        credentials["function_calling_type"] = "tool_call"
        credentials["extra_headers"] = {
            "HTTP-Referer": "https://dify.ai/",
            "X-Title": "Dify",
        }

    def _convert_prompt_message_to_dict(
        self, message: PromptMessage, credentials: dict | None = None
    ) -> dict:
        if isinstance(message, UserPromptMessage) and isinstance(message.content, list):
            sub_messages: list[dict] = []
            for content in message.content:
                if content.type == PromptMessageContentType.TEXT:
                    sub_messages.append({"type": "text", "text": content.data})
                elif content.type == PromptMessageContentType.IMAGE:
                    image_content: ImagePromptMessageContent = content
                    sub_messages.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_content.data,
                                "detail": image_content.detail.value,
                            },
                        }
                    )
            message_dict: dict = {"role": "user", "content": sub_messages}
            if message.name:
                message_dict["name"] = message.name
            return message_dict

        return super()._convert_prompt_message_to_dict(message, credentials)

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
        self._update_credential(model, credentials)
        return self._generate(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(model, credentials)
        return super().validate_credentials(model, credentials)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        self._update_credential(model, credentials)
        return super().get_customizable_model_schema(model, credentials)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        self._update_credential(model, credentials)
        return super().get_num_tokens(model, credentials, prompt_messages, tools)
