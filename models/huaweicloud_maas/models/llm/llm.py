from collections.abc import Generator
from typing import Optional, Union
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool


class HuaweiCloudMaasLargeLanguageModel(OAICompatLargeLanguageModel):
    endpoint_mapping = {
        "deepseek-v3.2": "https://api.modelarts-maas.com/v2",
        "deepseek-v3.2-exp": "https://api.modelarts-maas.com/v2",
        "deepseek-v3.1": "https://api.modelarts-maas.com/v2",
        "DeepSeek-V3": "https://api.modelarts-maas.com/v2",
        "deepseek-r1-250528": "https://api.modelarts-maas.com/v2",
        "DeepSeek-R1": "https://api.modelarts-maas.com/v2",
        "qwen3-235b-a22b": "https://api.modelarts-maas.com/v1",
        "qwen3-32b": "https://api.modelarts-maas.com/v1",
        "qwen3-30b-a3b": "https://api.modelarts-maas.com/v1",
        "qwen2.5-vl-72b": "https://api.modelarts-maas.com/v1",
        "qwen3-coder-480b-a35b-instruct": "https://api.modelarts-maas.com/v1",
        "Kimi-K2": "https://api.modelarts-maas.com/v2",
        "longcat-flash-chat": "https://api.modelarts-maas.com/v2",
    }

    thinking_mapping = {
        "deepseek-v3.2": "thinking.type.enabled",
        "deepseek-v3.2-exp": "thinking.type.enabled",
        "deepseek-v3.1": "thinking.type.enabled",
        "qwen3-235b-a22b": "chat_template_kwargs.enable_thinking.true",
        "qwen3-32b": "chat_template_kwargs.enable_thinking.true",
        "qwen3-30b-a3b": "chat_template_kwargs.enable_thinking.true",
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
                model, "thinking.type.enabled"
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
            model, "https://api.modelarts-maas.com/v1"
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
