from collections.abc import Generator
from typing import Optional, Union
from urllib.parse import urlparse
from dify_plugin import OAICompatLargeLanguageModel
import tiktoken
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
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
)


class YiLargeLanguageModel(OAICompatLargeLanguageModel):
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
        if model == "yi-vl-plus":
            prompt_message_except_system: list[PromptMessage] = []
            for message in prompt_messages:
                if not isinstance(message, SystemPromptMessage):
                    prompt_message_except_system.append(message)
            return super()._invoke(
                model,
                credentials,
                prompt_message_except_system,
                model_parameters,
                tools,
                stop,
                stream,
            )
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    def _num_tokens_from_string(
        self, model: str, text: str, tools: Optional[list[PromptMessageTool]] = None
    ) -> int:
        """
        Calculate num tokens for text completion model with tiktoken package.

        :param model: model name
        :param text: prompt text
        :param tools: tools for tool calling
        :return: number of tokens
        """
        encoding = tiktoken.get_encoding("cl100k_base")
        num_tokens = len(encoding.encode(text))
        if tools:
            num_tokens += self._num_tokens_for_tools(tools)
        return num_tokens

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        credentials["mode"] = "chat"
        credentials["openai_api_key"] = credentials["api_key"]
        if "endpoint_url" not in credentials or credentials["endpoint_url"] == "":
            credentials["endpoint_url"] = "https://api.lingyiwanwu.com/v1"
        else:
            parsed_url = urlparse(credentials["endpoint_url"])
            credentials["endpoint_url"] = (
                f"{parsed_url.scheme}://{parsed_url.netloc}"
            )

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity | None:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.TOOL_CALL,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ]
            if credentials.get("function_calling_type") == "tool_call"
            else [],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 8000)
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
                    name="max_tokens",
                    use_template="max_tokens",
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens", 8192)),
                    label=I18nObject(
                        en_us="Max Tokens",
                        zh_hans="指定生成结果长度的上限。如果生成结果截断，可以调大该参数",
                    ),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(
                        en_us="Top P",
                        zh_hans="控制生成结果的随机性。数值越小，随机性越弱；数值越大，随机性越强。",
                    ),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_k",
                    use_template="top_k",
                    label=I18nObject(en_us="Top K", zh_hans="取样数量"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="frequency_penalty",
                    use_template="frequency_penalty",
                    label=I18nObject(en_us="Frequency Penalty", zh_hans="重复惩罚"),
                    type=ParameterType.FLOAT,
                ),
            ],
        )
