from collections.abc import Generator
from typing import Optional, Union
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool


class HuaweiCloudMaasLargeLanguageModel(OAICompatLargeLanguageModel):
    _BASE_URL_V1 = "https://api.modelarts-maas.com/v1"
    _BASE_URL_V2 = "https://api.modelarts-maas.com/v2"
    _THINKING_PATH_XDS = "thinking.type.enabled"
    _THINKING_PATH_VLLM = "chat_template_kwargs.enable_thinking.true"

    endpoint_mapping = {
        "deepseek-v3.2": _BASE_URL_V2,
        "deepseek-v3.2-exp": _BASE_URL_V2,
        "deepseek-v3.1": _BASE_URL_V2,
        "DeepSeek-V3": _BASE_URL_V2,
        "deepseek-r1-250528": _BASE_URL_V2,
        "DeepSeek-R1": _BASE_URL_V2,
        "Kimi-K2": _BASE_URL_V2,
        "longcat-flash-chat": _BASE_URL_V2,
    }

    thinking_mapping = {
        "deepseek-v3.2": _THINKING_PATH_XDS,
        "deepseek-v3.2-exp": _THINKING_PATH_XDS,
        "deepseek-v3.1": _THINKING_PATH_XDS,
        "qwen3-235b-a22b": _THINKING_PATH_VLLM,
        "qwen3-32b": _THINKING_PATH_VLLM,
        "qwen3-30b-a3b": _THINKING_PATH_VLLM,
    }

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
        self._add_custom_parameters(model, credentials)
        self._add_function_call(model, credentials)

        enable_thinking = model_parameters.pop("enable_thinking", None)
        if enable_thinking is not None:
            path = HuaweiCloudMaasLargeLanguageModel.thinking_mapping.get(
                model, HuaweiCloudMaasLargeLanguageModel._THINKING_PATH_XDS
            ).split(".")
            if bool(enable_thinking) and path[2] == "enabled":
                value = "enabled"
            elif not bool(enable_thinking) and path[2] == "enabled":
                value = "disabled"
            else:
                value = bool(enable_thinking)
            model_parameters[path[0]] = {path[1]: value}

        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(model, credentials)
        super().validate_credentials(model, credentials)

    def _add_custom_parameters(self, model: str, credentials: dict) -> None:
        credentials["mode"] = "chat"
        endpoint_url = HuaweiCloudMaasLargeLanguageModel.endpoint_mapping.get(
            model, HuaweiCloudMaasLargeLanguageModel._BASE_URL_V1
        )
        credentials["endpoint_url"] = str(credentials.get("endpoint_url", endpoint_url))

    def _add_function_call(self, model: str, credentials: dict) -> None:
        model_schema = self.get_model_schema(model, credentials)
        if model_schema and {
            ModelFeature.TOOL_CALL,
            ModelFeature.MULTI_TOOL_CALL,
        }.intersection(model_schema.features or []):
            credentials["function_calling_type"] = "tool_call"

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        entity = super().get_customizable_model_schema(model, credentials)

        return entity
