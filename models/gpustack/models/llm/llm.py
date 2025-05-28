from collections.abc import Generator
import json
from urllib.parse import urljoin
import requests

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    DefaultParameterName,
    ModelFeature,
    ParameterRule,
    ParameterType,
    I18nObject,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin.errors.model import CredentialsValidateFailedError


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
        enable_thinking = model_parameters.pop("enable_thinking", None)
        if enable_thinking is not None:
            model_parameters["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}
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
        """
        Validate model credentials using requests to ensure compatibility with all providers following
         OpenAI's API standard.

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            credentials = self._get_compatible_credentials(credentials)
            headers = {"Content-Type": "application/json"}

            api_key = credentials.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            endpoint_url = credentials["endpoint_url"]
            if not endpoint_url.endswith("/"):
                endpoint_url += "/"

            # prepare the payload for a simple ping to the model
            data = {"model": model, "max_tokens": 50}

            completion_type = LLMMode.value_of(credentials["mode"])

            if completion_type is LLMMode.CHAT:
                data["messages"] = [
                    {"role": "user", "content": "ping"},
                ]
                endpoint_url = urljoin(endpoint_url, "chat/completions")
            elif completion_type is LLMMode.COMPLETION:
                data["prompt"] = "ping"
                endpoint_url = urljoin(endpoint_url, "completions")
            else:
                raise ValueError("Unsupported completion type for model configuration.")

            # send a post request to validate the credentials
            response = requests.post(endpoint_url, headers=headers, json=data, timeout=(10, 300))

            if response.status_code != 200:
                raise CredentialsValidateFailedError(
                    f"Credentials validation failed with status code {response.status_code}"
                )

            try:
                json_result = response.json()
            except json.JSONDecodeError as e:
                raise CredentialsValidateFailedError("Credentials validation failed: JSON decode error") from e

            if completion_type is LLMMode.CHAT and json_result.get("object", "") == "":
                json_result["object"] = "chat.completion"
            elif completion_type is LLMMode.COMPLETION and json_result.get("object", "") == "":
                json_result["object"] = "text_completion"

            if completion_type is LLMMode.CHAT and (
                "object" not in json_result or json_result["object"] != "chat.completion"
            ):
                raise CredentialsValidateFailedError(
                    "Credentials validation failed: invalid response object, must be 'chat.completion'"
                )
            elif completion_type is LLMMode.COMPLETION and (
                "object" not in json_result or json_result["object"] != "text_completion"
            ):
                raise CredentialsValidateFailedError(
                    "Credentials validation failed: invalid response object, must be 'text_completion'"
                )
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            raise CredentialsValidateFailedError(f"An error occurred during credentials validation: {str(ex)}") from ex

    def _add_custom_parameters(self, credentials: dict) -> None:
        credentials["mode"] = "chat"

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        credentials = credentials.copy()
        base_url = (
            credentials["endpoint_url"]
            .rstrip("/")
            .removesuffix("/v1")
            .removesuffix("/v1-openai")
        )
        credentials["endpoint_url"] = f"{base_url}/v1"
        return credentials

    def get_customizable_model_schema(self, model, credentials):
        entity =  super().get_customizable_model_schema(model, credentials)
        agent_thought_support = credentials.get("agent_thought_support", "not_supported")
        if agent_thought_support == "supported":
            try:
                entity.features.index(ModelFeature.AGENT_THOUGHT)
            except ValueError:
                entity.features.append(ModelFeature.AGENT_THOUGHT)

        structured_output_support = credentials.get("structured_output_support", "not_supported")
        if structured_output_support == "supported":
            entity.parameter_rules.append(ParameterRule(
                name=DefaultParameterName.RESPONSE_FORMAT.value,
                label=I18nObject(en_US="Response Format", zh_Hans="回复格式"),
                help=I18nObject(
                    en_US="Specifying the format that the model must output.",
                    zh_Hans="指定模型必须输出的格式。",
                ),
                type=ParameterType.STRING,
                options=["text", "json_object", "json_schema"],
                required=False,
            ))
            entity.parameter_rules.append(ParameterRule(
                name=DefaultParameterName.JSON_SCHEMA.value,
                use_template=DefaultParameterName.JSON_SCHEMA.value
            ))
        entity.parameter_rules += [
            ParameterRule(
                name="enable_thinking",
                label=I18nObject(en_US="Thinking mode", zh_Hans="思考模式"),
                help=I18nObject(
                    en_US="Whether to enable thinking mode, applicable to various thinking mode models deployed on reasoning frameworks such as vLLM and SGLang, for example Qwen3.",
                    zh_Hans="是否开启思考模式，适用于vLLM和SGLang等推理框架部署的多种思考模式模型，例如Qwen3。",
                ),
                type=ParameterType.BOOLEAN,
                required=False,
            )
        ]
        return entity
