import re
from contextlib import suppress
from typing import Mapping, Optional, Union, Generator
import json
import requests
from urllib.parse import urljoin
from requests.exceptions import ConnectionError, Timeout, RequestException

from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    I18nObject,
    ModelFeature,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMResult, LLMMode
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
    AssistantPromptMessage,
)
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel
from dify_plugin.errors.model import CredentialsValidateFailedError
from typing import List


def validate_lemonade_credentials(credentials: dict, model: str = None) -> None:
    """
    Validate Lemonade server credentials by checking the health endpoint and model availability.
    
    :param credentials: model credentials containing endpoint_url
    :param model: optional model name to validate availability
    :raises CredentialsValidateFailedError: if validation fails
    """

    if not model:
        raise CredentialsValidateFailedError("Please specify a model name")
    
    # Step 1: Check if the server is healthy
    try:
        headers = {"Content-Type": "application/json"}
        
        # Lemonade provider uses a fixed API key
        headers["Authorization"] = "Bearer lemonade"
        
        endpoint_url = credentials.get("endpoint_url")
        if not endpoint_url:
            raise CredentialsValidateFailedError("endpoint_url is required")
        
        if not endpoint_url.endswith("/"):
            endpoint_url += "/"
        
        # Use health endpoint to validate the server status
        health_endpoint = urljoin(endpoint_url, "/api/v1/health")
        
        # Send a GET request to check health endpoint
        response = requests.get(health_endpoint, headers=headers, timeout=(10, 300))
        
        if response.status_code != 200:
            raise CredentialsValidateFailedError(
                f"Credentials validation failed with status code {response.status_code} when checking {health_endpoint}"
            )
        
        try:
            json_result = response.json()
        except json.JSONDecodeError:
            raise CredentialsValidateFailedError("Credentials validation failed: JSON decode error")
        
        # Basic check for valid health response structure
        if "status" not in json_result:
            raise CredentialsValidateFailedError("Credentials validation failed: invalid response format")
        
        if json_result.get("status") != "ok":
            raise CredentialsValidateFailedError("Credentials validation failed: server status is not ok")
    
    except CredentialsValidateFailedError:
        raise
    except (ConnectionError, Timeout, RequestException):
        display_url = credentials.get("endpoint_url", "unknown")
        raise CredentialsValidateFailedError(
            f"Cannot connect to Lemonade server at {display_url}. "
            "Please ensure the Lemonade server is running and accessible."
            "You can download lemonade from lemonade-server.ai"
        )
    except Exception as ex:
        raise CredentialsValidateFailedError(str(ex))

    # Step 2: Check if the model is supported using the openai models endpoint
    try:
        response = requests.get(urljoin(credentials["endpoint_url"], "/api/v1/models"), headers=headers, timeout=(10, 300))
        if response.status_code != 200:
            raise CredentialsValidateFailedError(f"Credentials validation failed with status code {response.status_code} when checking {credentials['endpoint_url']}")
        
        try:
            models_result = response.json()
        except json.JSONDecodeError:
            raise CredentialsValidateFailedError("Failed to parse models response: JSON decode error")
        
        # Check if the response has the expected structure
        if "data" not in models_result:
            raise CredentialsValidateFailedError("Invalid models response format: missing 'data' field")
        
        # Extract model IDs from the response
        available_models = []
        for model_info in models_result.get("data", []):
            if isinstance(model_info, dict) and "id" in model_info:
                available_models.append(model_info["id"])
        
        # Check if the requested model is available
        if model not in available_models:
            base_url = credentials.get("endpoint_url", "").rstrip("/")
            management_url = f"{base_url}:8000/#model-management"
            raise CredentialsValidateFailedError(
                f"Model '{model}' is not available on the Lemonade server. "
                "Please pull the model first. You can find more information about it at "
                "https://lemonade-server.ai/docs/server/server_models/"
            )
            
    except CredentialsValidateFailedError:
        raise
    except Exception as ex:
        raise CredentialsValidateFailedError(f"Failed to validate model availability: {str(ex)}")
    
    


class LemonadeLargeLanguageModel(OAICompatLargeLanguageModel):
    # Pre-compiled regex for better performance
    _THINK_PATTERN = re.compile(r"^<think>.*?</think>\s*", re.DOTALL)

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        # Ensure credentials is a mutable dict and set custom parameters
        customized_credentials = dict(credentials)
        self._add_custom_parameters(customized_credentials)
        
        entity = super().get_customizable_model_schema(model, customized_credentials)

        agent_though_support = credentials.get("agent_though_support", "not_supported")
        if agent_though_support == "supported":
            try:
                entity.features.index(ModelFeature.AGENT_THOUGHT)
            except ValueError:
                entity.features.append(ModelFeature.AGENT_THOUGHT)

        structured_output_support = credentials.get("structured_output_support", "not_supported")
        if structured_output_support == "supported":
            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.RESPONSE_FORMAT.value,
                    label=I18nObject(en_US="Response Format", zh_Hans="回复格式"),
                    help=I18nObject(
                        en_US="Specifying the format that the model must output.",
                        zh_Hans="指定模型必须输出的格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["text", "json_object", "json_schema"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.JSON_SCHEMA.value,
                    use_template=DefaultParameterName.JSON_SCHEMA.value,
                )
            )

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

    @classmethod
    def _drop_analyze_channel(cls, prompt_messages: List[PromptMessage]) -> None:
        """
        Remove thinking content from assistant messages for better performance.

        Uses early exit and pre-compiled regex to minimize overhead.
        Args:
            prompt_messages:

        Returns:

        """
        for p in prompt_messages:
            # Early exit conditions
            if not isinstance(p, AssistantPromptMessage):
                continue
            if not isinstance(p.content, str):
                continue
            # Quick check to avoid regex if not needed
            if not p.content.startswith("<think>"):
                continue

            # Only perform regex substitution when necessary
            new_content = cls._THINK_PATTERN.sub("", p.content, count=1)
            # Only update if changed
            if new_content != p.content:
                p.content = new_content

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
        # Set required parameters for the OAI compatibility layer
        self._add_custom_parameters(credentials)
        
        # Compatibility adapter for Dify's 'json_schema' structured output mode.
        # The base class does not natively handle the 'json_schema' parameter. This block
        # translates it into a standard OpenAI-compatible request by:
        # 1. Injecting the JSON schema directly into the system prompt to guide the model.
        if model_parameters.get("response_format") == "json_schema":
            # Use .get() instead of .pop() for safety
            json_schema_str = model_parameters.get("json_schema")

            if json_schema_str:
                structured_output_prompt = (
                    "Your response must be a JSON object that validates against the following JSON schema, and nothing else.\n"
                    f"JSON Schema: ```json\n{json_schema_str}\n```"
                )

                existing_system_prompt = next(
                    (p for p in prompt_messages if p.role == PromptMessageRole.SYSTEM), None
                )
                if existing_system_prompt:
                    existing_system_prompt.content = (
                        structured_output_prompt + "\n\n" + existing_system_prompt.content
                    )
                else:
                    prompt_messages.insert(0, SystemPromptMessage(content=structured_output_prompt))

        enable_thinking = model_parameters.pop("enable_thinking", None)
        if enable_thinking is not None:
            model_parameters["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}

        # Remove thinking content from assistant messages for better performance.
        with suppress(Exception):
            self._drop_analyze_channel(prompt_messages)

        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        """
        Add custom parameters required for OAI compatibility layer.
        
        :param credentials: model credentials
        """
        # Set endpoint URL for OAI compatibility - crucial for proper routing
        if "endpoint_url" in credentials and "/api/v1" not in credentials["endpoint_url"]:
            endpoint_url = credentials["endpoint_url"].rstrip("/")
            # Set the base URL to include the API version path
            credentials["endpoint_url"] = endpoint_url + "/api/v1"
        
        # Set default parameters for OAI compatibility
        credentials["mode"] = "chat"
        credentials["function_calling_type"] = "tool_call"
        credentials["stream_function_calling"] = "supported"
        credentials["max_tokens_to_sample"] = 4096
        credentials["stream_mode_delimiter"] = '\n\n'
        credentials["stream_mode_auth"] = "not_use"

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials using shared validation utility.

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        # Set required parameters for the OAI compatibility layer
        self._add_custom_parameters(credentials)
        
        # Use shared validation function with model parameter
        validate_lemonade_credentials(credentials, model)
