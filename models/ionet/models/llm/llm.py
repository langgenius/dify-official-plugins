import logging
from typing import Generator, Optional, Union

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

DEFAULT_ENDPOINT_URL = "https://api.intelligence.io.solutions/api/v1"
DEFAULT_CONTEXT_SIZE = 128000
DEFAULT_MAX_TOKENS = 32768


class IonetLargeLanguageModel(OAICompatLargeLanguageModel):
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
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        self._add_custom_parameters(credentials)
        features: list[ModelFeature] = []
        if credentials.get("function_calling_type", "tool_call") == "tool_call":
            features.extend(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
            )
        if credentials.get("vision_support", "false") == "true":
            features.append(ModelFeature.VISION)

        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=features,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", DEFAULT_CONTEXT_SIZE)
                ),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_us="Temperature", zh_hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=4096,
                    min=1,
                    max=int(credentials.get("max_tokens", DEFAULT_MAX_TOKENS)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大 Token"),
                    type=ParameterType.INT,
                ),
            ],
        )

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        credentials.setdefault("endpoint_url", DEFAULT_ENDPOINT_URL)
        credentials.setdefault("mode", "chat")
