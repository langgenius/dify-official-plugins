from collections.abc import Generator
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool


class GPUStackLanguageModel(OAICompatLargeLanguageModel):
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
        model = model.strip()
        compatible_credentials = self._get_compatible_credentials(credentials)
        return super()._invoke(
            model,
            compatible_credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        compatible_credentials = self._get_compatible_credentials(credentials)
        super().validate_credentials(model, compatible_credentials)

    def _add_custom_parameters(self, credentials: dict) -> None:
        credentials["mode"] = "chat"

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        credentials = credentials.copy()
        base_url = credentials["endpoint_url"].rstrip("/").removesuffix("/v1")
        credentials["endpoint_url"] = f"{base_url}/v1"
        return credentials
