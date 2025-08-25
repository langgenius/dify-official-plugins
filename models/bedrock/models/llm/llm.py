# standard import
import base64
import json
import logging
from collections.abc import Generator
from typing import Optional, Union, cast

# 3rd import
import boto3  # type: ignore
from botocore.config import Config  # type: ignore
from botocore.exceptions import (  # type: ignore
    ClientError,
    EndpointConnectionError,
    NoRegionError,
    ServiceNotInRegionError,
    UnknownServiceError,
)

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
    PriceConfig,
)
from dify_plugin.entities.model.llm import (
    LLMMode,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
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
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from provider.get_bedrock_client import get_bedrock_client
from .cache_config import is_cache_supported, get_cache_config
from . import model_ids
from utils.inference_profile import (
    get_inference_profile_info,
    validate_inference_profile,
    extract_model_info_from_profile
)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)
ANTHROPIC_BLOCK_MODE_PROMPT = """You should always follow the instructions and output a valid {{block}} object.
The structure of the {{block}} object you can found in the instructions, use {"answer": "$your_answer"} as the default structure
if you are not sure about the structure.

<instructions>
{{instructions}}
</instructions>
"""  # noqa: E501


class BedrockLargeLanguageModel(LargeLanguageModel):
    # please refer to the documentation: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
    # TODO There is invoke issue: context limit on Cohere Model, will add them after fixed.
    CONVERSE_API_ENABLED_MODEL_INFO = [
        {"prefix": "us.deepseek", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "us.anthropic.claude", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "eu.anthropic.claude", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "apac.anthropic.claude", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "anthropic.claude", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "amazon.nova", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "us.amazon.nova", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "eu.amazon.nova", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "apac.amazon.nova", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "us.meta.llama", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "eu.meta.llama", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "apac.meta.llama", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "meta.llama", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "mistral.mistral-7b-instruct", "support_system_prompts": False, "support_tool_use": False},
        {"prefix": "mistral.mixtral-8x7b-instruct", "support_system_prompts": False, "support_tool_use": False},
        {"prefix": "mistral.mistral-large", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "mistral.mistral-small", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "cohere.command-r", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "amazon.titan", "support_system_prompts": False, "support_tool_use": False},
        {"prefix": "ai21.jamba-1-5", "support_system_prompts": True, "support_tool_use": False},
    ]

    @staticmethod
    def _find_model_info(model_id):
        for model in BedrockLargeLanguageModel.CONVERSE_API_ENABLED_MODEL_INFO:
            if model_id.startswith(model["prefix"]):
                return model
        logger.info(f"current model id: {model_id} did not support by Converse API")
        return None

    def _code_block_mode_wrapper(
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
        Code block mode wrapper for invoking large language model
        """
        if model_parameters.get("response_format"):
            stop = stop or []
            if "```\n" not in stop:
                stop.append("```\n")
            if "\n```" not in stop:
                stop.append("\n```")
            response_format = model_parameters.pop("response_format")
            format_prompt = SystemPromptMessage(
                content=ANTHROPIC_BLOCK_MODE_PROMPT.replace("{{instructions}}", prompt_messages[0].content).replace(
                    "{{block}}", response_format
                )
            )
            if len(prompt_messages) > 0 and isinstance(prompt_messages[0], SystemPromptMessage):
                prompt_messages[0] = format_prompt
            else:
                prompt_messages.insert(0, format_prompt)
            prompt_messages.append(AssistantPromptMessage(content=f"\n```{response_format}"))
        return self._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

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

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param tools: tools for tool calling
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        # Check if this is an inference profile model
        inference_profile_id = credentials.get("inference_profile_id")
        if inference_profile_id:
            # For inference profiles, we must use the converse API
            try:
                model_info = self._get_model_info(model, credentials, model_parameters)
                if model_info:
                    # Handle response_format for inference profiles only if underlying model is Anthropic
                    if model_parameters.get("response_format"):
                        # Check if the underlying model is Anthropic based
                        profile_info = get_inference_profile_info(inference_profile_id, credentials)
                        underlying_models = profile_info.get("models", [])
                        is_anthropic = False
                        
                        if underlying_models:
                            first_model_arn = underlying_models[0].get("modelArn", "")
                            if "foundation-model/" in first_model_arn:
                                underlying_model_id = first_model_arn.split("foundation-model/")[1]
                                is_anthropic = "anthropic.claude" in underlying_model_id
                        
                        if is_anthropic:
                            stop = stop or []
                            if "```\n" not in stop:
                                stop.append("```\n")
                            if "\n```" not in stop:
                                stop.append("\n```")
                            response_format = model_parameters.pop("response_format")
                            format_prompt = SystemPromptMessage(
                                content=ANTHROPIC_BLOCK_MODE_PROMPT.replace("{{instructions}}", prompt_messages[0].content).replace(
                                    "{{block}}", response_format
                                )
                            )
                            if len(prompt_messages) > 0 and isinstance(prompt_messages[0], SystemPromptMessage):
                                prompt_messages[0] = format_prompt
                            else:
                                prompt_messages.insert(0, format_prompt)
                            prompt_messages.append(AssistantPromptMessage(content=f"\n```{response_format}"))
                        else:
                            # For non-Anthropic models, just remove response_format parameter
                            model_parameters.pop("response_format", None)
                    
                    return self._generate_with_converse(
                        model_info, credentials, prompt_messages, model_parameters, stop, stream, user, tools, model
                    )
                else:
                    raise InvokeError(f"Could not get model information for inference profile {inference_profile_id}")
            except Exception as e:
                logger.error(f"Failed to invoke inference profile: {str(e)}")
                raise InvokeError(f"Failed to invoke inference profile {inference_profile_id}: {str(e)}")
        else:
            # Traditional model - try converse API first, then fall back if needed
            try:
                model_info = self._get_model_info(model, credentials, model_parameters)
                if model_info:
                    return self._generate_with_converse(
                        model_info, credentials, prompt_messages, model_parameters, stop, stream, user, tools, model
                    )
            except Exception as e:
                logger.error(f"Failed to get model info: {str(e)}")
            
            # Fallback to traditional model ID for non-converse API models
            model_name = model_parameters.get('model_name')
            if not model_name:
                raise InvokeError("Model name is required for non-converse API models")

        model_id = model_ids.get_model_id(model, model_name)
        # Store model_name in credentials for pricing calculation
        credentials_with_model = credentials.copy()
        credentials_with_model['model_parameters'] = {'model_name': model_name}
        return self._generate(model_id, credentials_with_model, prompt_messages, model_parameters, stop, stream, user)

    def _get_model_info(self, model: str, credentials: dict, model_parameters: dict) -> dict:
        """
        Get model information for converse API
        
        :param model: model name
        :param credentials: model credentials
        :param model_parameters: model parameters
        :return: model info dict with model ID and capabilities
        """
        inference_profile_id = credentials.get("inference_profile_id")
        if inference_profile_id:
            # Get the full ARN from the profile ID
            profile_info = get_inference_profile_info(inference_profile_id, credentials)
            profile_arn = profile_info.get("inferenceProfileArn")

            if not profile_arn:
                raise InvokeError(f"Could not get ARN for inference profile {inference_profile_id}")

            # Use inference profile ARN as model ID
            model_id = profile_arn
            logger.info(f"Using inference profile ARN: {model_id}")

            # Determine model capabilities from underlying models
            underlying_models = profile_info.get("models", [])
            model_info = None

            if underlying_models:
                first_model_arn = underlying_models[0].get("modelArn", "")
                # Extract model ID from ARN
                if "foundation-model/" in first_model_arn:
                    underlying_model_id = first_model_arn.split("foundation-model/")[1]
                    model_info = BedrockLargeLanguageModel._find_model_info(underlying_model_id)
                    if model_info:
                        # Use the inference profile ARN but with underlying model capabilities
                        model_info = model_info.copy()
                        model_info["model"] = model_id  # Use inference profile ARN for actual API call
                        logger.info(f"Using inference profile {model_id} with capabilities from {underlying_model_id}")
                        return model_info
            if not model_info:
                logger.info(f"Using inference profile {model_id} with default capabilities")
                return {
                    "model": model_id,
                    "support_system_prompts": True,
                    "support_tool_use": True
                }
        else:
            # Use traditional model ID resolution
            model_name = model_parameters.pop('model_name')
            model_id = model_ids.get_model_id(model, model_name)
            
            # Store model_name in credentials for pricing calculation
            if 'model_parameters' not in credentials:
                credentials['model_parameters'] = {}
            credentials['model_parameters']['model_name'] = model_name
            
            if model_parameters.pop('cross-region', False):
                region_name = credentials['aws_region']
                region_prefix = model_ids.get_region_area(region_name)
                if not region_prefix:
                    raise InvokeError(f'Region {region_name} Unsupport cross-region Inference')
                model_id = "{}.{}".format(region_prefix, model_id)

            model_info = BedrockLargeLanguageModel._find_model_info(model_id)
            if model_info:
                model_info["model"] = model_id
                return model_info
            
            return None

    def _generate_with_converse(
        self,
        model_info: dict,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
        tools: Optional[list[PromptMessageTool]] = None,
        model: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        """
        Invoke large language model with converse API

        :param model_info: model information
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :return: full response or stream response chunk generator result
        """
        bedrock_client = get_bedrock_client("bedrock-runtime", credentials)

        # Get cache checkpoint settings from model parameters
        system_cache_checkpoint = model_parameters.pop("system_cache_checkpoint", True)
        latest_two_messages_cache_checkpoint = model_parameters.pop("latest_two_messages_cache_checkpoint", False)
        logger.info(f"---cache_checkpoints--- system: {system_cache_checkpoint}, penultimate: {latest_two_messages_cache_checkpoint}")
        model_id = model_info["model"]
        print(f"[CACHE DEBUG] Model: {model_id}, Cache checkpoints - System: {system_cache_checkpoint}, Penultimate: {latest_two_messages_cache_checkpoint}")
        logger.info(f"[CACHE DEBUG] Model: {model_id}, Cache checkpoints - System: {system_cache_checkpoint}, Penultimate: {latest_two_messages_cache_checkpoint}")

        # Enable cache if either checkpoint is enabled
        cache_supported = is_cache_supported(model_id)
        print(f"[CACHE DEBUG] Model: {model_id}, Cache supported: {cache_supported}")
        logger.info(f"[CACHE DEBUG] Model: {model_id}, Cache supported: {cache_supported}")
        if cache_supported == False:
            system_cache_checkpoint = False
            latest_two_messages_cache_checkpoint = False

        # Convert messages with cache points if enabled
        system, prompt_message_dicts = self._convert_converse_prompt_messages(
            prompt_messages,
            model_id=model_id,
            system_cache_checkpoint=system_cache_checkpoint,
            latest_two_messages_cache_checkpoint=latest_two_messages_cache_checkpoint
        )
        inference_config, additional_model_fields = self._convert_converse_api_model_parameters(model_parameters, stop)

        parameters = {
            "modelId": model_info["model"],
            "messages": prompt_message_dicts,
            "inferenceConfig": inference_config,
            "additionalModelRequestFields": additional_model_fields,
        }

        if model_info["support_system_prompts"] and system and len(system) > 0:
            parameters["system"] = system

        if model_info["support_tool_use"] and tools:
            parameters["toolConfig"] = self._convert_converse_tool_config(tools=tools)
        try:
            # for issue #10976
            conversations_list = parameters["messages"]
            # if two consecutive user messages found, combine them into one message
            for i in range(len(conversations_list) - 2, -1, -1):
                if conversations_list[i]["role"] == conversations_list[i + 1]["role"]:
                    conversations_list[i]["content"].extend(conversations_list.pop(i + 1)["content"])

            if stream:
                response = bedrock_client.converse_stream(**parameters)
                return self._handle_converse_stream_response(
                    model_info["model"], credentials, response, prompt_messages
                )
            else:
                logger.info(f"converse: {parameters}")
                response = bedrock_client.converse(**parameters)

                # Log cache usage metrics if available
                if "usage" in response:
                    # Extract token usage
                    input_tokens = response["usage"].get("inputTokens", 0)
                    output_tokens = response["usage"].get("outputTokens", 0)

                    # Extract cache metrics if available
                    cache_read_tokens = response["usage"].get("cacheReadInputTokens", 0)
                    cache_write_tokens = response["usage"].get("cacheWriteInputTokens", 0)

                    # Always log the metrics for debugging
                    print(f"[CACHE METRICS] Model: {model_id}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    logger.info(f"[CACHE METRICS] Model: {model_id}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")

                    # Print the full response usage for debugging
                    print(f"[CACHE DEBUG] Response usage: {json.dumps(response['usage'], default=str)}")

                    # Log cache usage if any tokens were read or written
                    if cache_read_tokens > 0 or cache_write_tokens > 0:
                        logger.info(f"Cache metrics - Model: {model_id}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                        # If tokens were read from cache, log the savings
                        if cache_read_tokens > 0:
                            print(f"[CACHE HIT] {cache_read_tokens} tokens read from cache")
                            logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
                        elif cache_write_tokens > 0:
                            print(f"[CACHE WRITE] {cache_write_tokens} tokens written to cache")
                            logger.info(f"Cache write detected - {cache_write_tokens} tokens written to cache")
                else:
                    # Log if usage data is missing
                    print(f"[WARNING] No usage data in response")
                    logger.warning(f"No usage data in response")

                return self._handle_converse_response(model_info["model"], credentials, response, prompt_messages)
        except ClientError as ex:
            error_code = ex.response["Error"]["Code"]
            full_error_msg = f"{error_code}: {ex.response['Error']['Message']}"
            raise self._map_client_to_invoke_error(error_code, full_error_msg)
        except (EndpointConnectionError, NoRegionError, ServiceNotInRegionError) as ex:
            raise InvokeConnectionError(str(ex))

        except UnknownServiceError as ex:
            raise InvokeServerUnavailableError(str(ex))

        except Exception as ex:
            raise InvokeError(str(ex))

    def _handle_converse_response(
        self, model: str, credentials: dict, response: dict, prompt_messages: list[PromptMessage]
    ) -> LLMResult:
        """
        Handle llm chat response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: full response chunk generator result
        """
        response_content = response["output"]["message"]["content"]
        # transform assistant message to prompt message
        if response["stopReason"] == "tool_use":
            tool_calls = []
            text, tool_use = self._extract_tool_use(response_content)

            tool_call = AssistantPromptMessage.ToolCall(
                id=tool_use["toolUseId"],
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=tool_use["name"], arguments=json.dumps(tool_use["input"])
                ),
            )
            tool_calls.append(tool_call)

            assistant_prompt_message = AssistantPromptMessage(content=text, tool_calls=tool_calls)
        else:
            assistant_prompt_message = AssistantPromptMessage(content=response_content[0]["text"])

        # calculate num tokens
        if response["usage"]:
            # transform usage
            prompt_tokens = response["usage"]["inputTokens"]
            completion_tokens = response["usage"]["outputTokens"]

            # Log cache metrics if available
            cache_read_tokens = response["usage"].get("cacheReadInputTokens", 0)
            cache_write_tokens = response["usage"].get("cacheWriteInputTokens", 0)

            if cache_read_tokens > 0 or cache_write_tokens > 0:
                logger.info(f"Cache metrics - Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                # If tokens were read from cache, log the savings
                if cache_read_tokens > 0:
                    logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
        else:
            # calculate num tokens
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
            completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])

        # transform usage
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        result = LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
        )
        return result

    def _extract_tool_use(self, content: dict) -> tuple[str, dict]:
        tool_use = {}
        text = ""
        for item in content:
            if "toolUse" in item:
                tool_use = item["toolUse"]
            elif "text" in item:
                text = item["text"]
            else:
                raise ValueError(f"Got unknown item: {item}")
        return text, tool_use

    def _handle_converse_stream_response(
        self,
        model: str,
        credentials: dict,
        response: dict,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        """
        Handle llm chat stream response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: full response or stream response chunk generator result
        """

        try:
            full_assistant_content = ""
            return_model = None
            input_tokens = 0
            output_tokens = 0
            finish_reason = None
            index = 0
            tool_calls: list[AssistantPromptMessage.ToolCall] = []
            tool_use = {}
            reasoning_header_added = False
            reasoning_tailer_added = False

            for chunk in response["stream"]:
                if "messageStart" in chunk:
                    return_model = model
                elif "messageStop" in chunk:
                    finish_reason = chunk["messageStop"]["stopReason"]
                elif "contentBlockStart" in chunk:
                    tool = chunk["contentBlockStart"]["start"]["toolUse"]
                    tool_use["toolUseId"] = tool["toolUseId"]
                    tool_use["name"] = tool["name"]
                elif "metadata" in chunk:
                    # Safely extract usage data with proper error handling
                    if "usage" in chunk["metadata"]:
                        input_tokens = chunk["metadata"]["usage"].get("inputTokens", 0)
                        output_tokens = chunk["metadata"]["usage"].get("outputTokens", 0)

                        # Extract cache metrics if available
                        cache_read_tokens = chunk["metadata"]["usage"].get("cacheReadInputTokens", 0)
                        cache_write_tokens = chunk["metadata"]["usage"].get("cacheWriteInputTokens", 0)

                        # Always log the metrics for debugging
                        print(f"[STREAM CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                        logger.info(f"[STREAM CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")

                        # Print the full usage data for debugging
                        print(f"[STREAM USAGE DATA] {json.dumps(chunk['metadata']['usage'], default=str)}")

                        # Log cache usage if any tokens were read or written
                        if cache_read_tokens > 0 or cache_write_tokens > 0:
                            logger.info(f"Cache metrics - Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                            # If tokens were read from cache, log the savings
                            if cache_read_tokens > 0:
                                print(f"[STREAM CACHE HIT] {cache_read_tokens} tokens read from cache")
                                logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
                            elif cache_write_tokens > 0:
                                print(f"[STREAM CACHE WRITE] {cache_write_tokens} tokens written to cache")
                                logger.info(f"Cache write detected - {cache_write_tokens} tokens written to cache")
                    else:
                        # Log if usage data is missing
                        print(f"[STREAM WARNING] No usage data in metadata: {json.dumps(chunk['metadata'], default=str)}")
                        logger.warning(f"No usage data in metadata chunk: {json.dumps(chunk['metadata'], default=str)}")

                    usage = self._calc_response_usage(model, credentials, input_tokens, output_tokens)
                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=AssistantPromptMessage(content="", tool_calls=tool_calls),
                            finish_reason=finish_reason,
                            usage=usage,
                        ),
                    )
                elif "contentBlockDelta" in chunk:
                    delta = chunk["contentBlockDelta"]["delta"]
                    if "reasoningContent" in delta:
                        formatted_reasoning = ''
                        if "text" in delta["reasoningContent"]:
                            # Get reasoning content text
                            reasoning_text = delta["reasoningContent"]["text"] or ""

                            # start point of reasoningContent
                            if not reasoning_header_added:
                                formatted_reasoning = "<think>\n" + reasoning_text
                                reasoning_header_added = True
                            else:
                                formatted_reasoning = reasoning_text

                        # Update complete content, although it may not be needed here, but maintains code consistency
                        full_assistant_content += formatted_reasoning

                        assistant_prompt_message = AssistantPromptMessage(
                            content=formatted_reasoning
                        )
                        index = chunk["contentBlockDelta"]["contentBlockIndex"]
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=index + 1,
                                message=assistant_prompt_message,
                            ),
                        )
                    elif "text" in delta and delta["text"]:
                        text = delta["text"]

                        full_assistant_content += text

                        assistant_prompt_message = AssistantPromptMessage(
                            content=text or "",
                        )
                        index = chunk["contentBlockDelta"]["contentBlockIndex"]
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=index + 1,
                                message=assistant_prompt_message,
                            ),
                        )
                    elif "toolUse" in delta:
                        if "input" not in tool_use:
                            tool_use["input"] = ""
                        tool_use["input"] += delta["toolUse"]["input"]
                elif "contentBlockStop" in chunk:
                    # If reasoning was started but never completed (no text content followed)
                    # we need to close the thinking tag
                    if reasoning_tailer_added is False and full_assistant_content.startswith("<think>"):
                        assistant_prompt_message = AssistantPromptMessage(
                            content="\n</think>"
                        )
                        full_assistant_content += "\n</think>"
                        reasoning_tailer_added = True
                        index += 1
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=index + 1,
                                message=assistant_prompt_message,
                            ),
                        )

                    if "input" in tool_use:
                        tool_call = AssistantPromptMessage.ToolCall(
                            id=tool_use["toolUseId"],
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name=tool_use["name"], arguments=tool_use["input"]
                            ),
                        )
                        tool_calls.append(tool_call)
                        tool_use = {}

        except Exception as ex:
            raise InvokeError(str(ex))

    def _convert_converse_api_model_parameters(
        self, model_parameters: dict, stop: Optional[list[str]] = None
    ) -> tuple[dict, dict]:
        inference_config = {}
        additional_model_fields = {}
        if "max_tokens" in model_parameters:
            inference_config["maxTokens"] = model_parameters["max_tokens"]
        elif "max_new_tokens" in model_parameters:
            inference_config["maxTokens"] = model_parameters["max_new_tokens"]

        if "temperature" in model_parameters:
            inference_config["temperature"] = model_parameters["temperature"]

        if "top_p" in model_parameters:
            inference_config["topP"] = model_parameters["temperature"]

        if stop:
            inference_config["stopSequences"] = stop

        if "top_k" in model_parameters:
            additional_model_fields["top_k"] = model_parameters["top_k"]

        if "anthropic_beta" in model_parameters:
            additional_model_fields["anthropic_beta"] = list(map(lambda v:v.strip(), model_parameters["anthropic_beta"].strip().split(",")))

        # process reasoning related parameters, construct nested reasoning_config structure
        if "reasoning_type" in model_parameters:
            reasoning_type = model_parameters["reasoning_type"]
            if reasoning_type:
                reasoning_config = {
                    "type": "enabled"
                }
                # set budget_tokens, ensure at least 1024
                budget_tokens = 1024
                if "reasoning_budget" in model_parameters:
                    budget_tokens = max(1024, model_parameters["reasoning_budget"])
                # make sure budget_tokens is less than max_tokens
                if "max_tokens" in model_parameters:
                    budget_tokens = min(budget_tokens, model_parameters["max_tokens"] - 1)
                    reasoning_config["budget_tokens"] = budget_tokens
                additional_model_fields["reasoning_config"] = reasoning_config
                inference_config["temperature"] = 1
                if "topP" in inference_config:
                    del inference_config["topP"]

        return inference_config, additional_model_fields

    def _convert_converse_prompt_messages(self, prompt_messages: list[PromptMessage], model_id: str = None,
        system_cache_checkpoint: bool = True, latest_two_messages_cache_checkpoint: bool = False) -> tuple[list, list[dict]]:
        """
        Convert prompt messages to dict list and system
        Add cache points for supported models when enable_cache is True

        :param prompt_messages: List of prompt messages to convert
        :param model_id: Model ID to check for cache support
        :param system_cache_checkpoint: Whether to add cache checkpoint to system message
        :param latest_two_messages_cache_checkpoint: Whether to add cache checkpoint to the latest two user messages
        :return: Tuple of system messages and prompt message dicts
        """
        system = []
        prompt_message_dicts = []

        # Check if model supports caching
        cache_config = get_cache_config(model_id)

        # Process system messages first
        system_messages = [msg for msg in prompt_messages if isinstance(msg, SystemPromptMessage)]
        other_messages = [msg for msg in prompt_messages if not isinstance(msg, SystemPromptMessage)]

        # Add system messages
        for message in system_messages:
            message.content = message.content.strip()
            system.append({"text": message.content})

            # Add cache point to system if it's not empty and caching is supported for system field
        # and system_cache_checkpoint is enabled
        if system and cache_config and "system" in cache_config["supported_fields"] and system_cache_checkpoint:
            system.append({"cachePoint": {"type": "default"}})
            print(f"[CACHE DEBUG] Added cache point to system messages for model: {model_id}")

            # Process other messages
        for message in other_messages:
            message_dict = self._convert_prompt_message_to_dict(message)
            prompt_message_dicts.append(message_dict)

            # Only add cache point to messages if supported and latest_two_messages_cache_checkpoint is enabled
        if cache_config and "messages" in cache_config["supported_fields"] and latest_two_messages_cache_checkpoint:
            # Find all user messages
            user_message_indices = [i for i, msg in enumerate(prompt_message_dicts) if msg["role"] in ["user"]]

            # Add cache point to available user messages (up to the latest two)
            if len(user_message_indices) > 0:
                # Get indices for the latest messages (either one or two depending on availability)
                indices_to_cache = user_message_indices[-min(2, len(user_message_indices)):]
                print(f"[CACHE DEBUG] indices_to_cacheis {indices_to_cache}")
                for idx in indices_to_cache:
                    message = prompt_message_dicts[idx]
                    print(f"[CACHE DEBUG] current idx is {idx}")

                    # Check if content is a list
                    if isinstance(message["content"], list):
                        # Add cache point to the content array
                        message["content"].append({"cachePoint": {"type": "default"}})
                        print(f"[CACHE DEBUG] Added cache point to user message content list at index {idx} for model: {model_id}")
                    else:
                        # If content is not a list, convert it to a list with the original content and add cache point
                        original_content = message["content"]
                        message["content"] = [{"text": original_content}, {"cachePoint": {"type": "default"}}]
                        print(f"[CACHE DEBUG] Converted user message content to list and added cache point at index {idx} for model: {model_id}")

                    prompt_message_dicts[idx] = message
        # Print the final system and messages for debugging
        # print(f"[CACHE DEBUG] System messages: {json.dumps(system, default=str)}")
        print(f"[CACHE DEBUG] Prompt messages: {json.dumps(prompt_message_dicts, default=str)}")

        return system, prompt_message_dicts

    def _convert_converse_tool_config(self, tools: Optional[list[PromptMessageTool]] = None) -> dict:
        tool_config = {}
        configs = []
        if tools:
            for tool in tools:
                configs.append(
                    {
                        "toolSpec": {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": {"json": tool.parameters},
                        }
                    }
                )
            tool_config["tools"] = configs
            return tool_config

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dict
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": [{"text": message.content}]}
            else:
                sub_messages = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(TextPromptMessageContent, message_content)
                        sub_message_dict = {"text": message_content.data}
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_content = cast(ImagePromptMessageContent, message_content)
                        data_split = message_content.data.split(";base64,")
                        mime_type = data_split[0].replace("data:", "")
                        base64_data = data_split[1]
                        image_content = base64.b64decode(base64_data)

                        if mime_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
                            raise ValueError(
                                f"Unsupported image type {mime_type}, "
                                f"only support image/jpeg, image/png, image/gif, and image/webp"
                            )

                        sub_message_dict = {
                            "image": {"format": mime_type.replace("image/", ""), "source": {"bytes": image_content}}
                        }
                        sub_messages.append(sub_message_dict)

                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {
                "role" : "assistant",
                "content": []
            }

            if message.tool_calls:
                for tool_use in message.tool_calls:
                    message_dict["content"].append({
                        "toolUse": {
                            "toolUseId": tool_use.id,
                            "name": tool_use.function.name,
                            "input": json.loads(tool_use.function.arguments),
                        }
                    })
            else:
                message_dict = {"role": "assistant", "content": [{"text": message.content}]}
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = [{"text": message.content}]
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": message.tool_call_id,
                            "content": [{"json": {"text": message.content}}],
                        }
                    }
                ],
            }
        else:
            raise ValueError(f"Got unknown type {message}")
        return message_dict

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage] | str,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages or message string
        :param tools: tools for tool calling
        :return:md = genai.GenerativeModel(model)
        """
        if model.startswith('us.') or model.startswith('eu.'):
            prefix = model.split(".")[1]
            model_name = model.split(".")[2]
        else:
            prefix = model.split(".")[0]
            model_name = model.split(".")[1]

        if isinstance(prompt_messages, str):
            prompt = prompt_messages
        else:
            prompt = self._convert_messages_to_prompt(prompt_messages, prefix, model_name)

        return self._get_num_tokens_by_gpt2(prompt)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        Get customizable model schema for inference profiles
        
        :param model: model name
        :param credentials: model credentials
        :return: AIModelEntity
        """
        inference_profile_id = credentials.get("inference_profile_id")
        if inference_profile_id:
            try:
                # Get inference profile info from AWS directly
                profile_info = get_inference_profile_info(inference_profile_id, credentials)
                
                # Extract model name from profile
                profile_name = profile_info.get("inferenceProfileName", model)
                context_length = int(credentials.get("context_length", 4096))
                
                # Find matching predefined model based on underlying model ARN
                default_pricing = None
                matched_features = []
                matched_parameter_rules = []
                matched_model_properties = {
                    "mode": LLMMode.CHAT,
                    "context_size": context_length,
                }
                underlying_models = profile_info.get("models", [])
                
                if underlying_models:
                    first_model_arn = underlying_models[0].get("modelArn", "")
                    if "foundation-model/" in first_model_arn:
                        underlying_model_id = first_model_arn.split("foundation-model/")[1]
                        model_schemas = self.predefined_models()
                        
                        # Try to get model-specific pricing based on the underlying model ID
                        # Map model ID to model name for pricing lookup
                        model_name_for_pricing = self._map_model_id_to_name(underlying_model_id)
                        
                        # First try to find individual model schema for pricing
                        if model_name_for_pricing:
                            individual_pricing = self._get_model_specific_pricing("", model_name_for_pricing, model_schemas)
                            if individual_pricing:
                                default_pricing = individual_pricing
                        
                        # Then find matching schema for features and parameters
                        for model_schema in model_schemas:
                            if self._model_id_matches_schema(underlying_model_id, model_schema):
                                # Use individual pricing if found, otherwise fall back to schema pricing
                                if not default_pricing:
                                    default_pricing = model_schema.pricing
                                    
                                matched_features = model_schema.features or []
                                # Extract allowed parameters from model schema, excluding model_name since it's determined by inference profile
                                matched_parameter_rules = self._get_inference_profile_parameter_rules(model_schema, underlying_model_id)
                                if model_schema.model_properties:
                                    matched_model_properties.update(model_schema.model_properties)
                                    # Override context_size with user-specified value
                                    matched_model_properties["context_size"] = context_length
                                break
                
                # Fallback to first predefined model pricing if no match found
                if not default_pricing:
                    model_schemas = self.predefined_models()
                    if model_schemas:
                        default_pricing = model_schemas[0].pricing
                
                # Use the user-provided model name exactly as entered
                # Create custom model entity based on inference profile
                return AIModelEntity(
                    model=model,
                    label=I18nObject(en_US=model),
                    model_type=ModelType.LLM,
                    features=matched_features,
                    fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
                    model_properties=matched_model_properties,
                    parameter_rules=matched_parameter_rules,
                    pricing=default_pricing
                )
            except Exception as e:
                logger.error(f"Failed to get inference profile schema: {str(e)}")
                # Create fallback custom model entity with inference profile name
                context_length = int(credentials.get("context_length", 4096))
                model_schemas = self.predefined_models()
                default_pricing = model_schemas[0].pricing if model_schemas else None
                # For fallback, extract parameters from first model schema
                fallback_parameter_rules = []
                if model_schemas:
                    # For fallback, we don't have underlying_model_id, so pass None to get all params except model_name
                    fallback_parameter_rules = self._get_inference_profile_parameter_rules(model_schemas[0], None)
                fallback_features = model_schemas[0].features if model_schemas else []
                fallback_model_properties = {
                    "mode": LLMMode.CHAT,
                    "context_size": context_length,
                }
                # Use first model's properties as fallback, but keep user-specified context_size
                if model_schemas and model_schemas[0].model_properties:
                    fallback_model_properties.update(model_schemas[0].model_properties)
                    fallback_model_properties["context_size"] = context_length
                
                return AIModelEntity(
                    model=model,
                    label=I18nObject(en_US=model),
                    model_type=ModelType.LLM,
                    features=fallback_features,
                    fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
                    model_properties=fallback_model_properties,
                    parameter_rules=fallback_parameter_rules,
                    pricing=default_pricing
                )
        
        # This should not be reached for inference profile models, but keep as final fallback
        return None


    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            # Check if this is an inference profile based custom model
            inference_profile_id = credentials.get("inference_profile_id")
            if inference_profile_id:
                # Validate inference profile directly
                validate_inference_profile(inference_profile_id, credentials)
                logger.info(f"Successfully validated inference profile: {inference_profile_id}")
                return
            
            # Traditional model validation
            foundation_model_ids = self._list_foundation_models(credentials=credentials)
            cris_prefix = model_ids.get_region_area(credentials.get("aws_region"))
            if model.startswith(cris_prefix):
                model = model.split('.', 1)[1]
            logger.info(f"get model_ids: {foundation_model_ids}")
            if model not in foundation_model_ids:
                raise ValueError(f"model id: {model} not found in bedrock")
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))


    def _list_foundation_models(self, credentials: dict) -> list[str]:
        """
        List available foundation models from Amazon Bedrock
        """
        def remove_context_window_suffix(model_ids):
            """
            使用正则表达式移除模型ID中的context window后缀
            """
            cleaned_ids = []
            for model_id in model_ids:
                if model_id.endswith('k'):
                    parts = model_id.split(':')
                    model_id_no_suffix = ':'.join(parts[:-1])
                    cleaned_ids.append(model_id_no_suffix)
                else:
                    cleaned_ids.append(model_id)
            return list(set(cleaned_ids))
        try:
            bedrock_client = get_bedrock_client("bedrock", credentials)
            response = bedrock_client.list_foundation_models()
            models = []
            for model in response.get('modelSummaries', []):
                models.append(model.get('modelId'))
            return remove_context_window_suffix(models)
        except Exception as e:
            logger.info(f"Error listing Bedrock foundation models: {str(e)}")
            # Fall back to config if there's an error
            raise e

    def _convert_one_message_to_text(
        self, message: PromptMessage, model_prefix: str, model_name: Optional[str] = None
    ) -> str:
        """
        Convert a single message to a string.

        :param message: PromptMessage to convert.
        :return: String representation of the message.
        """
        human_prompt_prefix = ""
        human_prompt_postfix = ""
        ai_prompt = ""

        content = message.content

        if isinstance(message, UserPromptMessage):
            body = content
            if isinstance(content, list):
                body = "".join([c.data for c in content if c.type == PromptMessageContentType.TEXT])
            message_text = f"{human_prompt_prefix} {body} {human_prompt_postfix}"
        elif isinstance(message, AssistantPromptMessage):
            message_text = f"{ai_prompt} {content}"
        elif isinstance(message, SystemPromptMessage):
            message_text = content
        elif isinstance(message, ToolPromptMessage):
            message_text = f"{human_prompt_prefix} {message.content}"
        else:
            raise ValueError(f"Got unknown type {message}")

        return message_text

    def _convert_messages_to_prompt(
            self, messages: list[PromptMessage], model_prefix: str, model_name: Optional[str] = None
    ) -> str:
        """
        Format a list of messages into a full prompt for the Anthropic, Amazon and Llama models

        :param messages: List of PromptMessage to combine.
        :param model_name: specific model name.Optional,just to distinguish llama2 and llama3
        :return: Combined string with necessary human_prompt and ai_prompt tags.
        """
        if not messages:
            return ""

        messages = messages.copy()  # don't mutate the original list
        if not isinstance(messages[-1], AssistantPromptMessage):
            messages.append(AssistantPromptMessage(content=""))

        text = "".join(self._convert_one_message_to_text(message, model_prefix, model_name) for message in messages)

        # trim off the trailing ' ' that might come from the "Assistant: "
        return text.rstrip()

    def _create_payload(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        stop: Optional[list[str]] = None,
        stream: bool = True,
    ):
        """
        Create payload for bedrock api call depending on model provider
        """
        payload = {}
        if model.startswith('us.') or model.startswith('eu.') or model.startswith('apac.'):
            model_prefix = model.split(".")[1]
        else:
            model_prefix = model.split(".")[0]

        if model_prefix == "ai21":
            payload["temperature"] = model_parameters.get("temperature")
            payload["topP"] = model_parameters.get("topP")
            payload["maxTokens"] = model_parameters.get("maxTokens")
            payload["prompt"] = self._convert_messages_to_prompt(prompt_messages, model_prefix)

            if model_parameters.get("presencePenalty"):
                payload["presencePenalty"] = {model_parameters.get("presencePenalty")}
            if model_parameters.get("frequencyPenalty"):
                payload["frequencyPenalty"] = {model_parameters.get("frequencyPenalty")}
            if model_parameters.get("countPenalty"):
                payload["countPenalty"] = {model_parameters.get("countPenalty")}

        elif model_prefix == "cohere":
            payload = {**model_parameters}
            payload["prompt"] = prompt_messages[0].content
            payload["stream"] = stream

        else:
            raise ValueError(f"Got unknown model prefix {model_prefix}")

        return payload

    def _generate(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        """
        Invoke large language model

        :param model: model name
        :param credentials: credentials kwargs
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        bedrock_client = get_bedrock_client("bedrock-runtime", credentials)

        model_prefix = model.split(".")[0]
        payload = self._create_payload(model, prompt_messages, model_parameters, stop, stream)

        # need workaround for ai21 models which doesn't support streaming
        if stream and model_prefix != "ai21":
            invoke = runtime_client.invoke_model_with_response_stream
        else:
            invoke = runtime_client.invoke_model

        try:
            body_jsonstr = json.dumps(payload)
            response = invoke(modelId=model, contentType="application/json", accept="*/*", body=body_jsonstr)
        except ClientError as ex:
            error_code = ex.response["Error"]["Code"]
            full_error_msg = f"{error_code}: {ex.response['Error']['Message']}"
            raise self._map_client_to_invoke_error(error_code, full_error_msg)

        except (EndpointConnectionError, NoRegionError, ServiceNotInRegionError) as ex:
            raise InvokeConnectionError(str(ex))

        except UnknownServiceError as ex:
            raise InvokeServerUnavailableError(str(ex))

        except Exception as ex:
            raise InvokeError(str(ex))

        if stream:
            return self._handle_generate_stream_response(model, credentials, response, prompt_messages)

        return self._handle_generate_response(model, credentials, response, prompt_messages)

    def _handle_generate_response(
        self, model: str, credentials: dict, response: dict, prompt_messages: list[PromptMessage]
    ) -> LLMResult:
        """
        Handle llm response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response
        """
        response_body = json.loads(response.get("body").read().decode("utf-8"))

        finish_reason = response_body.get("error")

        if finish_reason is not None:
            raise InvokeError(finish_reason)

        # get output text and calculate num tokens based on model / provider
        model_prefix = model.split(".")[0]

        if model_prefix == "ai21":
            output = response_body.get("completions")[0].get("data").get("text")
            prompt_tokens = len(response_body.get("prompt").get("tokens"))
            completion_tokens = len(response_body.get("completions")[0].get("data").get("tokens"))

        elif model_prefix == "cohere":
            output = response_body.get("generations")[0].get("text")
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
            completion_tokens = self.get_num_tokens(model, credentials, output or "")

        else:
            raise ValueError(f"Got unknown model prefix {model_prefix} when handling block response")

        # construct assistant message from output
        assistant_prompt_message = AssistantPromptMessage(content=output)

        # calculate usage
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        # construct response
        result = LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
        )

        return result

    def _handle_generate_stream_response(
        self, model: str, credentials: dict, response: dict, prompt_messages: list[PromptMessage]
    ) -> Generator:
        """
        Handle llm stream response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator result
        """
        model_prefix = model.split(".")[0]
        if model_prefix == "ai21":
            response_body = json.loads(response.get("body").read().decode("utf-8"))

            content = response_body.get("completions")[0].get("data").get("text")
            finish_reason = response_body.get("completions")[0].get("finish_reason")

            prompt_tokens = len(response_body.get("prompt").get("tokens"))
            completion_tokens = len(response_body.get("completions")[0].get("data").get("tokens"))
            usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
            yield LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(
                    index=0, message=AssistantPromptMessage(content=content), finish_reason=finish_reason, usage=usage
                ),
            )
            return

        stream = response.get("body")
        if not stream:
            raise InvokeError("No response body")

        index = -1
        for event in stream:
            chunk = event.get("chunk")

            if not chunk:
                exception_name = next(iter(event))
                full_ex_msg = f"{exception_name}: {event[exception_name]['message']}"
                raise self._map_client_to_invoke_error(exception_name, full_ex_msg)

            payload = json.loads(chunk.get("bytes").decode())

            model_prefix = model.split(".")[0]
            if model_prefix == "cohere":
                content_delta = payload.get("text")
                finish_reason = payload.get("finish_reason")

            else:
                raise ValueError(f"Got unknown model prefix {model_prefix} when handling stream response")

            # transform assistant message to prompt message
            assistant_prompt_message = AssistantPromptMessage(
                content=content_delta or "",
            )
            index += 1

            if not finish_reason:
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(index=index, message=assistant_prompt_message),
                )

            else:
                # get num tokens from metrics in last chunk
                prompt_tokens = payload["amazon-bedrock-invocationMetrics"]["inputTokenCount"]
                completion_tokens = payload["amazon-bedrock-invocationMetrics"]["outputTokenCount"]

                # transform usage
                usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index, message=assistant_prompt_message, finish_reason=finish_reason, usage=usage
                    ),
                )

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the ermd = genai.GenerativeModel(model) error type thrown to the caller
        The value is the md = genai.GenerativeModel(model) error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke emd = genai.GenerativeModel(model) error mapping
        """
        return {
            InvokeConnectionError: [],
            InvokeServerUnavailableError: [],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [],
        }

    def _map_client_to_invoke_error(self, error_code: str, error_msg: str) -> type[InvokeError]:
        """
        Map client error to invoke error

        :param error_code: error code
        :param error_msg: error message
        :return: invoke error
        """

        if error_code == "AccessDeniedException":
            return InvokeAuthorizationError(error_msg)
        elif error_code in {"ResourceNotFoundException", "ValidationException"}:
            return InvokeBadRequestError(error_msg)
        elif error_code in {"ThrottlingException", "ServiceQuotaExceededException"}:
            return InvokeRateLimitError(error_msg)
        elif error_code in {
            "ModelTimeoutException",
            "ModelErrorException",
            "InternalServerException",
            "ModelNotReadyException",
        }:
            return InvokeServerUnavailableError(error_msg)
        elif error_code == "ModelStreamErrorException":
            return InvokeConnectionError(error_msg)

        return InvokeError(error_msg)

    def _get_inference_profile_parameter_rules(self, model_schema, underlying_model_id: str = None) -> list:
        """
        Extract allowed parameter rules from model schema for inference profiles
        
        :param model_schema: The predefined model schema
        :param underlying_model_id: The underlying model ID (for model-specific filtering)
        :return: List of parameter rules suitable for inference profiles
        """
        if not model_schema.parameter_rules:
            return []
        
        # Always exclude model_name since it's determined by inference profile
        excluded_params = ['model_name']
        
        # Apply model-specific filtering if underlying_model_id is available
        allowed_parameter_rules = []
        for rule in model_schema.parameter_rules:
            if rule.name in excluded_params:
                continue
                
            # For Anthropic models, include response_format only if it's an Anthropic model
            if rule.name == 'response_format':
                if underlying_model_id and "anthropic.claude" not in underlying_model_id:
                    continue  # Skip response_format for non-Anthropic models
                elif not underlying_model_id:
                    # Fallback case: only include if this is an Anthropic schema
                    if not (hasattr(model_schema, 'model') and model_schema.model == "anthropic claude"):
                        continue
            
            allowed_parameter_rules.append(rule)
        
        return allowed_parameter_rules

    def _model_id_matches_schema(self, model_id: str, model_schema) -> bool:
        """
        Check if a model ID matches a predefined model schema
        
        :param model_id: The model ID from inference profile (e.g., anthropic.claude-3-5-sonnet-20241022-v2:0)
        :param model_schema: The predefined model schema
        :return: True if the model ID matches the schema
        """
        # Extract the model family from the model ID and check individual models first
        if "anthropic.claude" in model_id:
            return (model_schema.model == "anthropic claude" or 
                   model_schema.model.startswith("claude-"))
        elif "amazon.nova" in model_id:
            return (model_schema.model == "amazon nova" or 
                   model_schema.model.startswith("nova-"))
        elif "cohere.command" in model_id:
            return (model_schema.model == "cohere" or 
                   model_schema.model.startswith("cohere-"))
        elif "ai21" in model_id:
            return model_schema.model == "ai21"
        elif "meta.llama" in model_id:
            return model_schema.model == "meta"
        elif "mistral" in model_id:
            return model_schema.model == "mistral"
        elif "deepseek" in model_id:
            return model_schema.model == "deepseek"
        
        return False
    
    def _map_model_id_to_name(self, model_id: str) -> Optional[str]:
        """
        Map a Bedrock model ID to a model name for pricing lookup.
        
        :param model_id: The Bedrock model ID (e.g., 'anthropic.claude-3-5-sonnet-20241022-v2:0')
        :return: The model name or None
        """
        # Reverse lookup from model_ids
        from . import model_ids
        
        # Remove version suffix if present
        base_model_id = model_id.split(':')[0] if ':' in model_id else model_id
        
        # Search through all model families
        for family, models in model_ids.BEDROCK_MODEL_IDS.items():
            for name, id_value in models.items():
                # Compare base IDs without version
                base_id_value = id_value.split(':')[0] if ':' in id_value else id_value
                if base_id_value == base_model_id or id_value == model_id:
                    return name
        
        return None
    
    def _get_model_specific_pricing(self, model: str, model_name: str, model_schemas: list):
        """
        Get model-specific pricing based on model name.
        First tries to find exact model match from model_configurations directory, then falls back to family pricing.
        
        :param model: The model family (e.g., 'anthropic-claude')
        :param model_name: The specific model name (e.g., 'Claude 3.5 Sonnet')
        :param model_schemas: List of predefined model schemas
        :return: Pricing configuration or None
        """
        # Create model name mapping for individual model files
        model_name_mapping = {
            # Claude models
            'Claude 4.0 Sonnet': 'claude-4-sonnet',
            'Claude 4.0 Opus': 'claude-4-opus',
            'Claude 3.7 Sonnet': 'claude-3-7-sonnet',
            'Claude 3.5 Haiku': 'claude-3-5-haiku',
            'Claude 3.5 Sonnet': 'claude-3-5-sonnet', 
            'Claude 3.5 Sonnet V2': 'claude-3-5-sonnet',
            'Claude 3 Haiku': 'claude-3-haiku',
            'Claude 3 Sonnet': 'claude-3-sonnet',
            'Claude 3 Opus': 'claude-3-opus',
            # Nova models
            'Nova Micro': 'nova-micro',
            'Nova Lite': 'nova-lite',
            'Nova Pro': 'nova-pro',
            # Cohere models
            'Command': 'cohere-command',
            'Command Light': 'cohere-command-light',
            'Command R': 'cohere-command-r',
            'Command R+': 'cohere-command-rplus'
        }
        
        # First, try to load individual model pricing from model_configurations subdirectory
        individual_model_name = model_name_mapping.get(model_name)
        if individual_model_name:
            try:
                import os
                import yaml
                # Get the directory of this file
                current_dir = os.path.dirname(os.path.abspath(__file__))
                individual_model_path = os.path.join(current_dir, 'model_configurations', f'{individual_model_name}.yaml')
                
                if os.path.exists(individual_model_path):
                    with open(individual_model_path, 'r', encoding='utf-8') as f:
                        model_config = yaml.safe_load(f)
                        if 'pricing' in model_config:
                            return model_config['pricing']
            except Exception as e:
                # If individual model file loading fails, continue to fallback
                pass
        
        # Fallback: try to find individual model in existing schemas (for backward compatibility)
        if individual_model_name:
            for schema in model_schemas:
                if schema.model == individual_model_name:
                    return schema.pricing
        
        # If no model family provided, skip family pricing lookup
        if not model:
            return None
        
        # If no individual model found, try family pricing
        # Look for exact model match first
        for schema in model_schemas:
            if schema.model == model:
                return schema.pricing
        
        # If exact match not found, try with different formats
        # Sometimes model might be passed as 'anthropic claude' vs 'anthropic-claude'
        model_variants = [
            model.replace('-', ' '),  # 'anthropic-claude' -> 'anthropic claude'
            model.replace(' ', '-'),  # 'anthropic claude' -> 'anthropic-claude'
            model.lower(),
            model.lower().replace('-', ' '),
            model.lower().replace(' ', '-')
        ]
        
        for schema in model_schemas:
            for variant in model_variants:
                if schema.model == variant:
                    return schema.pricing
                    
        return None
    
    def _calc_response_usage(self, model: str, credentials: dict, prompt_tokens: int, completion_tokens: int):
        """
        Calculate response usage with per-model pricing support.
        
        :param model: model name
        :param credentials: model credentials
        :param prompt_tokens: number of prompt tokens
        :param completion_tokens: number of completion tokens
        :return: LLMUsage
        """
        # Get model-specific pricing if available
        model_parameters = credentials.get('model_parameters', {})
        model_name = model_parameters.get('model_name')
        
        if model_name:
            # Try to get model-specific pricing
            model_schemas = self.predefined_models()
            model_pricing = self._get_model_specific_pricing(model, model_name, model_schemas)
            
            if model_pricing:
                # Use model-specific pricing
                from dify_plugin.entities.model.llm import LLMUsage
                
                # Handle both dict and object pricing formats
                if isinstance(model_pricing, dict):
                    input_price = float(model_pricing['input'])
                    output_price = float(model_pricing['output'])
                    unit_price = float(model_pricing['unit'])
                    currency = model_pricing.get('currency', 'USD')
                else:
                    # Object with attributes
                    input_price = float(model_pricing.input)
                    output_price = float(model_pricing.output)
                    unit_price = float(model_pricing.unit)
                    currency = model_pricing.currency
                
                # Calculate costs correctly: (tokens × price) ÷ unit_tokens
                input_cost = (prompt_tokens * input_price) / (1.0 / unit_price)
                output_cost = (completion_tokens * output_price) / (1.0 / unit_price)
                
                # Round to avoid floating point precision issues
                input_cost = round(input_cost, 8)
                output_cost = round(output_cost, 8)
                total_cost = round(input_cost + output_cost, 8)
                
                # Get latency from parent class by calling it first
                parent_usage = super()._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
                
                return LLMUsage(
                    prompt_tokens=prompt_tokens,
                    prompt_unit_price=input_price,
                    prompt_price_unit=unit_price,
                    prompt_price=input_cost,
                    completion_tokens=completion_tokens,
                    completion_unit_price=output_price,
                    completion_price_unit=unit_price,
                    completion_price=output_cost,
                    total_tokens=prompt_tokens + completion_tokens,
                    total_price=total_cost,
                    currency=currency,
                    latency=parent_usage.latency,  # Use parent's latency calculation
                )
        
        # Fallback to parent class implementation
        return super()._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
    
