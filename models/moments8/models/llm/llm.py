import json
import logging
import requests
from collections.abc import Generator
from typing import Optional, Union, Dict, Any

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.errors.model import (
    CredentialsValidateFailedError, InvokeError
)
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
    ModelFeature,
    ModelPropertyKey,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage
)
from dify_plugin.entities.model.message import (
    PromptMessage,
    AssistantPromptMessage,
    PromptMessageTool, PromptMessageRole,
)

logger = logging.getLogger(__name__)


class Moments8LargeLanguageModel(LargeLanguageModel):
    """
    Model class for moments8 large language model.
    """

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
        """
        Invoke large language model
        """
        logger.info(f"Invoking moments8 model: {model}")

        # 1. Prepare request headers and URL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {credentials['moments8_api_key']}"
        }
        endpoint = credentials.get('endpoint_url',
                                   "https://mas.moments8.com/api/v1/chat/completions")

        # 2. Convert prompt messages format
        messages = []
        for msg in prompt_messages:
            role = "user"
            if msg.role == PromptMessageRole.SYSTEM:
                role = "system"
            elif msg.role == PromptMessageRole.ASSISTANT:
                role = "assistant"

            messages.append({"role": role, "content": msg.content})

        # 3. Prepare request payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **model_parameters
        }

        # 4. Add stop sequences
        if stop:
            payload["stop"] = stop

        # 5. Add user ID
        if user:
            payload["user"] = user

        # 6. Send request
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                stream=stream
            )

            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise InvokeError(error_msg)

            # 7. Handle stream response
            if stream:
                return self._handle_stream_response(response)
            # 8. Handle non-stream response
            else:
                return self._handle_non_stream_response(response.json())

        except requests.exceptions.RequestException as e:
            logger.exception("Network error during API request")
            raise InvokeError(f"Network error: {str(e)}")

    def _handle_stream_response(self, response: requests.Response) -> Generator:
        """Handle stream response"""
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                # Skip comment lines in event stream
                if decoded_line.startswith(":"):
                    continue

                # Extract JSON data (format: data: {...})
                if decoded_line.startswith("data:"):
                    json_str = decoded_line[5:].strip()
                    if json_str == "[DONE]":
                        break

                    try:
                        data = json.loads(json_str)
                        # Extract model information
                        model_name = data.get("model", "")
                        system_fingerprint = data.get("system_fingerprint")
                        choices = data.get("choices", [])

                        if choices:
                            # Process each choice in the response
                            for choice in choices:
                                index = choice.get("index", 0)
                                delta = choice.get("delta", {})
                                finish_reason = choice.get("finish_reason")

                                # Handle content delta
                                content = delta.get("content", "")
                                role = delta.get("role", "assistant")

                                # Create assistant message for content chunks
                                message = None
                                if content or role:
                                    message = AssistantPromptMessage(
                                        content=content,
                                        role=role
                                    )

                                # Create LLM chunk delta
                                chunk_delta = LLMResultChunkDelta(
                                    index=index,
                                    message=message,
                                    finish_reason=finish_reason,
                                    usage=None  # Usage not available in streaming
                                )

                                # Yield LLM result chunk
                                yield LLMResultChunk(
                                    model=model_name,
                                    system_fingerprint=system_fingerprint,
                                    delta=chunk_delta
                                )

                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON: {json_str}")

    def _handle_non_stream_response(self, response_data: dict) -> LLMResult:
        """Handle non-stream response"""
        # Extract response data
        model_name = response_data.get("model", "")
        system_fingerprint = response_data.get("system_fingerprint")
        choices = response_data.get("choices", [])
        usage_data = response_data.get("usage", {})

        if not choices:
            raise InvokeError("Invalid response format from API")

        # Process the first choice
        choice = choices[0]
        message_data = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        # Create assistant message
        message = AssistantPromptMessage(
            content=message_data.get("content", ""),
            role=message_data.get("role", "assistant")
        )

        # Create usage information
        usage = LLMUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0)
        )

        # Return LLM result
        return LLMResult(
            model=model_name,
            message=message,
            usage=usage,
            system_fingerprint=system_fingerprint
        )

    # ... (other methods remain unchanged) ...
    def get_num_tokens(
            self,
            model: str,
            credentials: dict,
            prompt_messages: list[PromptMessage],
            tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """
        Get number of tokens for given prompt messages
        """
        # 简化的token估算方法
        total_text = " ".join([msg.content for msg in prompt_messages])
        return len(total_text) // 4  # 近似估算：1个token≈4个字符

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials
        """
        if not credentials.get("moments8_api_key"):
            raise CredentialsValidateFailedError("Missing API key in credentials")

        if not credentials.get("endpoint_url"):
            logger.warning("No custom endpoint provided, using default")

    def get_customizable_model_schema(
            self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        Return model schema with customizable parameters
        """
        return AIModelEntity(
            model=model,
            label=I18nObject(zh_Hans=model, en_US=model),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.TOOL_CALL,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: 8000,
                ModelPropertyKey.MAX_TOKENS: 4096
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                    type=ParameterType.FLOAT,
                    default=0.7,
                    min=0.0,
                    max=1.0
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    label=I18nObject(en_US="Max Tokens", zh_Hans="最大标记"),
                    type=ParameterType.INT,
                    default=1024,
                    min=1,
                    max=4096
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                    type=ParameterType.FLOAT,
                    default=0.9,
                    min=0.0,
                    max=1.0
                ),
                ParameterRule(
                    name="stream",
                    use_template="stream",
                    label=I18nObject(en_US="Stream", zh_Hans="流式输出"),
                    type=ParameterType.BOOLEAN,
                    default=True
                )
            ]
        )

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeError: [
                requests.exceptions.RequestException,
                ValueError,
                KeyError
            ]
        }