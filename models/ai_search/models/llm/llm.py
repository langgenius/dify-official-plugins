import json
import logging
import time
from typing import cast, Optional, Union, Generator, List
from collections.abc import Generator

from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from tencentcloud.common import credential
from tencentcloud.common.exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.es.v20250101 import es_client, models

logger = logging.getLogger(__name__)


class AiSearchLargeLanguageModel(LargeLanguageModel):
    """
    Tencent Cloud Large Language Model Plugin
    """

    # Configuration constants
    API_ENDPOINT = "es.ai.tencentcloudapi.com"
    API_VERSION = "2025-01-01"
    DEFAULT_API_REGION = "ap-beijing"

    # Supported models list
    SUPPORTED_MODELS = [
        "deepseek-r1",
        "deepseek-v3",
        "deepseek-r1-distill-qwen-32b",
        "hunyuan-turbo",
        "hunyuan-large",
        "hunyuan-large-longcontext",
        "hunyuan-standard",
        "hunyuan-standard-256K"
    ]

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
    ) -> Union[LLMResult, Generator]:
        """
        Invoke Tencent Cloud LLM service
        """
        self.started_at = time.perf_counter()

        try:
            # Parameter validation
            self._validate_input_params(model, prompt_messages, model_parameters)

            # Initialize client
            client = self._setup_es_client(credentials)

            # Convert prompt messages
            messages_dict = self._convert_prompt_messages_to_dicts(prompt_messages)

            # Build request parameters
            params = self._build_request_params(
                model=model,
                messages=messages_dict,
                model_parameters=model_parameters,
                stream=stream,
                tools=tools
            )

            # Create request object
            req = models.ChatCompletionsRequest()
            req.from_json_string(json.dumps(params))

            # Call API
            resp = client.ChatCompletions(req)

            # Process response based on stream mode
            if stream:
                return self._handle_stream_response(model, prompt_messages, resp)
            else:
                return self._handle_response(model, credentials, prompt_messages, resp)

        except TencentCloudSDKException as e:
            logger.error(f"TencentCloud SDK Error: {str(e)}", exc_info=True)
            raise InvokeError(f"TencentCloud ES API request failed: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise InvokeError(f"Processing failed: {str(e)}")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate Tencent Cloud credentials
        """
        try:
            # Validate required fields
            if not credentials.get("secret_id") or not credentials.get("secret_key"):
                raise CredentialsValidateFailedError("Missing required credentials: secret_id and secret_key")

            # Validate model support
            if model not in self.SUPPORTED_MODELS:
                raise CredentialsValidateFailedError(f"Model {model} is not supported")

            # Initialize client
            client = self._setup_es_client(credentials)

            # Test API call with minimal parameters
            params = {
                "ModelName": model,
                "Messages": [{"Role": "user", "Content": "credentials validation test"}],
                "Stream": False,
            }

            req = models.ChatCompletionsRequest()
            req.from_json_string(json.dumps(params))

            response = client.ChatCompletions(req)

            # Check response structure
            if not response:
                raise CredentialsValidateFailedError("API returned empty response")

            logger.info("Credentials validation successful")

        except TencentCloudSDKException as e:
            raise CredentialsValidateFailedError(f"API authentication failed: {e.message}")
        except CredentialsValidateFailedError:
            raise
        except Exception as e:
            raise CredentialsValidateFailedError(f"Validation error: {str(e)}")

    def _setup_es_client(self, credentials: dict) -> es_client.EsClient:
        """
        Standardized Tencent Cloud client initialization
        """
        try:
            secret_id = credentials.get("secret_id")
            secret_key = credentials.get("secret_key")

            if not secret_id or not secret_key:
                raise CredentialsValidateFailedError("Missing required credentials: secret_id and secret_key")

            cred = credential.Credential(secret_id, secret_key)

            http_profile = HttpProfile()
            http_profile.endpoint = self.API_ENDPOINT
            http_profile.reqTimeout = 600

            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile

            # Get region from credentials or use default
            region = credentials.get("region", self.DEFAULT_API_REGION)

            return es_client.EsClient(cred, region, client_profile)
        except KeyError as e:
            raise CredentialsValidateFailedError(f"Missing credential field: {str(e)}")
        except Exception as e:
            raise CredentialsValidateFailedError(f"Client setup failed: {str(e)}")

    def _validate_input_params(self, model: str, prompt_messages: list[PromptMessage],
                               model_parameters: dict) -> None:
        """
        Validate input parameters
        """
        if model not in self.SUPPORTED_MODELS:
            raise InvokeError(f"Model {model} is not supported")

        if not prompt_messages or not isinstance(prompt_messages, list):
            raise InvokeError("Prompt messages must be a non-empty list")

        temperature = model_parameters.get("temperature")
        if temperature is not None:
            if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2:
                raise InvokeError("Temperature must be a number between 0 and 2")

        top_p = model_parameters.get("top_p")
        if top_p is not None:
            if not isinstance(top_p, (int, float)) or top_p < 0 or top_p > 1:
                raise InvokeError("TopP must be a number between 0 and 1")

    def _build_request_params(self, model: str, messages: list[dict],
                              model_parameters: dict, stream: bool,
                              tools: list[PromptMessageTool] | None = None) -> dict:
        """
        Build request parameters
        """
        params = {
            "ModelName": model,
            "Messages": messages,
            "Stream": stream,
        }

        if model_parameters.get("temperature") is not None:
            params["Temperature"] = model_parameters["temperature"]

        if model_parameters.get("top_p") is not None:
            params["TopP"] = model_parameters["top_p"]

        if model_parameters.get("online_search") is not None:
            params["OnlineSearch"] = model_parameters["online_search"]

        if tools and len(tools) > 0:
            params["Tools"] = self._convert_tools_to_api_format(tools)

            tool_choice = model_parameters.get("tool_choice", "required")
            params["ToolChoice"] = tool_choice

            if tool_choice == "custom" and len(tools) > 0:
                params["CustomTool"] = self._convert_tools_to_api_format(tools)[0]

        return params

    def _convert_tools_to_api_format(self, tools: list[PromptMessageTool]) -> list[dict]:
        """
        Convert Dify tools format to Tencent Cloud API format
        """
        api_tools = []

        for tool in tools:
            tool_dict = {
                "Type": "function",
                "Function": {
                    "Name": tool.name,
                    "Description": tool.description or "",
                    "Parameters": tool.parameters or {}
                }
            }
            api_tools.append(tool_dict)

        return api_tools
    def _convert_prompt_messages_to_dicts(self, prompt_messages: list[PromptMessage]) -> list[dict]:
        """
        Convert PromptMessage list to Tencent Cloud API format
        """
        dict_list = []
        for message in prompt_messages:
            if isinstance(message, AssistantPromptMessage):
                dict_list.append(self._convert_assistant_message(message))
            elif isinstance(message, ToolPromptMessage):
                dict_list.append(self._convert_tool_message(message))
            elif isinstance(message, UserPromptMessage):
                dict_list.append(self._convert_user_message(message))
            else:
                dict_list.append(self._convert_generic_message(message))

        return dict_list

    def _convert_assistant_message(self, message: AssistantPromptMessage) -> dict:
        """
        Convert assistant message
        """
        tool_calls = message.tool_calls
        if tool_calls and len(tool_calls) > 0:
            dict_tool_calls = [
                {
                    "Id": tool_call.id,
                    "Type": tool_call.type,
                    "Function": {
                        "Name": tool_call.function.name,
                        "Arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in tool_calls
            ]
            return {
                "Role": message.role.value,
                "Content": message.content or "",
                "ToolCalls": dict_tool_calls
            }
        else:
            return {
                "Role": message.role.value,
                "Content": message.content or ""
            }

    def _convert_tool_message(self, message: ToolPromptMessage) -> dict:
        """
        Convert tool message
        """
        return {
            "Role": message.role.value,
            "Content": message.content,
            "ToolCallId": message.tool_call_id
        }

    def _convert_user_message(self, message: UserPromptMessage) -> dict:
        """
        Convert user message
        """
        if isinstance(message.content, str):
            return {
                "Role": message.role.value,
                "Content": message.content
            }
        else:
            # Handle multimodal content
            contents = []
            for content in message.content:
                if content.type == PromptMessageContentType.TEXT:
                    content = cast(TextPromptMessageContent, content)
                    contents.append({
                        "Type": "text",
                        "Text": content.data
                    })
                elif content.type == PromptMessageContentType.IMAGE:
                    content = cast(ImagePromptMessageContent, content)
                    contents.append({
                        "Type": "image_url",
                        "ImageUrl": {"Url": content.data}
                    })
            return {
                "Role": message.role.value,
                "Contents": contents
            }

    def _convert_generic_message(self, message: PromptMessage) -> dict:
        """
        Convert generic message
        """
        return {
            "Role": message.role.value,
            "Content": message.content or ""
        }

    def _handle_stream_response(
            self,
            model: str,
            prompt_messages: list[PromptMessage],
            response: Generator
    ) -> Generator[LLMResultChunk, None, None]:
        """
        Handle stream response
        """
        try:
            # Check if response is generator type (streaming)
            if not hasattr(response, '__iter__'):
                raise InvokeError(
                    f"Expected iterable stream response but got {type(response)}. "
                    f"The API may not support streaming for this model."
                )

            # Handle real stream response
            return self._process_stream_response(model, prompt_messages, response)

        except Exception as e:
            logger.error(f"Error processing stream response: {str(e)}", exc_info=True)
            raise InvokeError(f"Error processing stream response: {str(e)}")

    def _process_stream_response(
            self,
            model: str,
            prompt_messages: list[PromptMessage],
            response: Generator
    ) -> Generator[LLMResultChunk, None, None]:
        """
        Process real stream response - Refactored main function
        """
        is_reasoning = False
        tool_calls = []

        for index, event in enumerate(response):
            try:
                # Process single event using helper function
                chunk = self._process_single_stream_event(
                    event, index, model, prompt_messages, is_reasoning, tool_calls
                )

                if chunk:
                    # Update state variables
                    is_reasoning = chunk.delta.message.content.startswith(
                        "<think>") if chunk.delta.message.content else is_reasoning
                    tool_calls = chunk.delta.message.tool_calls or tool_calls

                    yield chunk

            except Exception as e:
                logger.error(f"Error processing stream event: {str(e)}", exc_info=True)
                raise InvokeError(f"Error processing stream response: {str(e)}")

    def _process_single_stream_event(
            self,
            event: object,
            index: int,
            model: str,
            prompt_messages: list[PromptMessage],
            is_reasoning: bool,
            current_tool_calls: list
    ) -> Optional[LLMResultChunk]:
        """
        Process single stream event - Extracted core logic
        """
        # Extract response data from event
        response_data = self._extract_response_data_from_event(event)
        if not response_data:
            return None

        # Extract choice from response
        choice = self._extract_choice_from_response(response_data)
        if not choice:
            return None

        # Extract message from choice
        message = self._extract_message_from_choice(choice)
        if not message:
            return None

        # Extract content from message
        content = ""
        if isinstance(message, dict):
            content = message.get('Content', "")
        elif hasattr(message, 'Content'):
            content = getattr(message, 'Content', "")

        # Process reasoning content
        content, updated_reasoning = self._wrap_thinking_by_reasoning_content(message, is_reasoning)

        # Extract tool calls from message
        tool_calls_data = []
        if isinstance(message, dict):
            tool_calls_data = message.get('ToolCalls', [])
        elif hasattr(message, 'ToolCalls'):
            tool_calls_data = getattr(message, 'ToolCalls', [])

        tool_calls = self._extract_response_tool_calls(tool_calls_data) if tool_calls_data else current_tool_calls

        # Create assistant message
        assistant_msg = AssistantPromptMessage(
            content=content if not tool_calls else "",
            tool_calls=tool_calls
        )

        # Create delta chunk
        delta_chunk = LLMResultChunkDelta(
            index=index,
            message=assistant_msg
        )

        return LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=delta_chunk
        )

    def _extract_response_data_from_event(self, event: object) -> Optional[dict]:
        """
        Extract response data from event object
        """
        try:
            # Handle dictionary type event with data field
            if isinstance(event, dict) and 'data' in event:
                try:
                    data_content = event['data']
                    if isinstance(data_content, str):
                        parsed_data = json.loads(data_content)
                        return parsed_data.get('Response')
                    else:
                        return data_content.get('Response') if isinstance(data_content, dict) else data_content
                except json.JSONDecodeError:
                    return None

            # Handle object with Response attribute
            elif hasattr(event, 'Response'):
                return event.Response

            # Handle object with data attribute
            elif hasattr(event, 'data'):
                data_attr = getattr(event, 'data')
                try:
                    if isinstance(data_attr, str):
                        parsed_data = json.loads(data_attr)
                        return parsed_data.get('Response')
                    else:
                        return data_attr.get('Response') if isinstance(data_attr, dict) else data_attr
                except json.JSONDecodeError:
                    return None

            # Use event object directly
            else:
                return event

        except Exception:
            return None

    def _extract_choice_from_response(self, response_data: dict) -> Optional[dict]:
        """
        Extract choice from response data
        """
        try:
            # Extract choices from response data
            choices = []
            if isinstance(response_data, dict):
                choices = response_data.get('Choices', [])
            elif hasattr(response_data, 'Choices'):
                choices = getattr(response_data, 'Choices', [])

            if not choices:
                return None

            # Return first choice or the choices object itself
            return choices[0] if isinstance(choices, list) and choices else choices

        except Exception:
            return None

    def _extract_message_from_choice(self, choice) -> Optional[dict]:
        """
        Extract message from choice object
        """
        try:
            # Extract message from choice
            message = None
            if isinstance(choice, dict):
                message = choice.get('Message', choice)
            elif hasattr(choice, 'Message'):
                message = getattr(choice, 'Message')
            else:
                message = choice

            return message if message else None

        except Exception:
            return None
    def _handle_response(
            self,
            model: str,
            credentials: dict,
            prompt_messages: list[PromptMessage],
            response: object
    ) -> LLMResult:
        """
        Handle non-stream response
        """
        try:
            if hasattr(response, 'Response'):
                response_obj = response.Response
            else:
                response_obj = response

            choices = getattr(response_obj, 'Choices', [])
            if not choices or len(choices) == 0:
                error_msg = getattr(response_obj, 'Error', 'No choices in response')
                raise InvokeError(f"API response error: {error_msg}")

            choice = choices[0]
            message = getattr(choice, 'Message', None)

            if not message:
                raise InvokeError("Empty message in response")

            content = getattr(message, 'Content', "")
            usage_data = getattr(response_obj, 'Usage', {})

            # Create assistant message
            assistant_msg = AssistantPromptMessage(
                content=content,
                tool_calls=[]
            )

            # Handle tool calls
            tool_calls_data = getattr(message, 'ToolCalls', [])
            if tool_calls_data and len(tool_calls_data) > 0:
                assistant_msg.tool_calls = self._extract_response_tool_calls(tool_calls_data)
                assistant_msg.content = ""

            # Create usage structure
            usage = self._calc_response_usage(
                model,
                credentials,
                getattr(usage_data, 'PromptTokens', 0),
                getattr(usage_data, 'CompletionTokens', 0)
            )

            result = LLMResult(
                model=model,
                prompt_messages=prompt_messages,
                message=assistant_msg,
                usage=usage
            )

            return result

        except Exception as e:
            logger.error(f"Error processing non-stream response: {str(e)}", exc_info=True)
            raise InvokeError(f"Error processing response: {str(e)}")

    def _extract_response_tool_calls(self, tool_calls: list) -> list:
        """
        Extract tool calls from API response
        """
        extracted_tool_calls = []

        for tool_call in tool_calls:
            try:
                extracted_tool_calls.append({
                    "id": getattr(tool_call, 'Id', ""),
                    "type": getattr(tool_call, 'Type', ""),
                    "function": {
                        "name": getattr(getattr(tool_call, 'Function', None), 'Name', ""),
                        "arguments": getattr(getattr(tool_call, 'Function', None), 'Arguments', "")
                    }
                })
            except Exception as e:
                logger.warning(f"Failed to extract tool call: {str(e)}")
                continue

        return extracted_tool_calls

    def _wrap_thinking_by_reasoning_content(self, delta: object, is_reasoning: bool) -> tuple[str, bool]:
        """
        Wrap reasoning content with HTML tags
        """
        content = ""
        reasoning_content = ""

        # Extract content and reasoning_content
        if isinstance(delta, dict):
            content = delta.get('Content', "")
            reasoning_content = delta.get('ReasoningContent', "")
        else:
            content = getattr(delta, 'Content', "")
            reasoning_content = getattr(delta, 'ReasoningContent', "")

        if reasoning_content:
            if not is_reasoning:
                content = "<think>\n" + reasoning_content
                is_reasoning = True
            else:
                content = reasoning_content
        elif is_reasoning and content:
            content = "\n</think>" + content
            is_reasoning = False

        return content, is_reasoning

    def get_num_tokens(
            self,
            model: str,
            credentials: dict,
            prompt_messages: list[PromptMessage],
            tools: list[PromptMessageTool] | None = None,
    ) -> int:
        """
        Calculate token count for prompt messages
        """
        if not prompt_messages:
            return 0

        prompt = self._convert_messages_to_prompt(prompt_messages)
        return self._get_num_tokens_by_gpt2(prompt)

    def _convert_messages_to_prompt(self, messages: list[PromptMessage]) -> str:
        """
        Convert messages to single prompt string
        """
        return "\n".join(
            f"{message.role.value}: {message.content}"
            for message in messages
            if message.content
        )

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Error type mapping
        """
        return {
            InvokeError: [TencentCloudSDKException, json.JSONDecodeError]
        }