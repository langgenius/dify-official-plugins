import logging
from collections.abc import Generator
from typing import Optional, Union

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

logger = logging.getLogger(__name__)


class FuturMixLargeLanguageModel(OAICompatLargeLanguageModel):
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
        self._add_custom_parameters(credentials, model)
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials, model)
        super().validate_credentials(model, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict, model: str) -> None:
        credentials["endpoint_url"] = "https://futurmix.ai/v1"
        credentials.setdefault("mode", "chat")

        # Enable function calling for models that support it, only if not already set
        if "function_calling_type" not in credentials:
            model_lower = model.lower()
            if any(
                name in model_lower
                for name in ["gpt-", "claude-", "gemini-"]
            ):
                credentials["function_calling_type"] = "tool_call"

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            model_type=ModelType.LLM,
            features=(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
                if credentials.get("function_calling_type") == "tool_call"
                else []
            ),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: cls._safe_int(
                    credentials.get("context_size"), 128000
                ),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=4096,
                    min=1,
                    max=cls._safe_int(credentials.get("max_tokens_to_sample"), 16384),
                    label=I18nObject(en_US="Max Tokens", zh_Hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="frequency_penalty",
                    use_template="frequency_penalty",
                    label=I18nObject(
                        en_US="Frequency Penalty", zh_Hans="频率惩罚"
                    ),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="presence_penalty",
                    use_template="presence_penalty",
                    label=I18nObject(
                        en_US="Presence Penalty", zh_Hans="存在惩罚"
                    ),
                    type=ParameterType.FLOAT,
                ),
            ],
        )

    @staticmethod
    def _safe_int(value, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
