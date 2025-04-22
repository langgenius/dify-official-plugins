# standard import
import base64
import json
import logging
from collections.abc import Generator
from typing import Optional, Union, cast, Dict, Any

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
        {"prefix": "anthropic.claude-v2", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "us.deepseek", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "anthropic.claude-v1", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "us.anthropic.claude-3", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "eu.anthropic.claude-3", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "anthropic.claude-3", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "us.meta.llama3-2", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "meta.llama", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "mistral.mistral-7b-instruct", "support_system_prompts": False, "support_tool_use": False},
        {"prefix": "mistral.mixtral-8x7b-instruct", "support_system_prompts": False, "support_tool_use": False},
        {"prefix": "mistral.mistral-large", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "mistral.mistral-small", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "cohere.command-r", "support_system_prompts": True, "support_tool_use": True},
        {"prefix": "amazon.titan", "support_system_prompts": False, "support_tool_use": False},
        {"prefix": "ai21.jamba-1-5", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "amazon.nova", "support_system_prompts": True, "support_tool_use": False},
        {"prefix": "us.amazon.nova", "support_system_prompts": True, "support_tool_use": False},
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

        model_info = BedrockLargeLanguageModel._find_model_info(model)
        if model_info:
            model_info["model"] = model
            # invoke models via boto3 converse API
            return self._generate_with_converse(
                model_info, credentials, prompt_messages, model_parameters, stop, stream, user, tools
            )
        # invoke other models via boto3 client
        return self._generate(model, credentials, prompt_messages, model_parameters, stop, stream, user)

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
        
        # Check if cache is enabled in model parameters
        enable_cache = model_parameters.pop("enable_cache", False)
        logger.info(f"---enable_cache---: {enable_cache}")
        model_id = model_info["model"]
        print(f"[CACHE DEBUG] Model: {model_id}, Cache enabled: {enable_cache}")
        logger.info(f"[CACHE DEBUG] Model: {model_id}, Cache enabled: {enable_cache}")

        cache_supported = is_cache_supported(model_id) and enable_cache
        print(f"[CACHE DEBUG] Model: {model_id}, Cache supported: {cache_supported}")
        logger.info(f"[CACHE DEBUG] Model: {model_id}, Cache supported: {cache_supported}")
        
        # Convert messages with cache points if enabled
        system, prompt_message_dicts = self._convert_converse_prompt_messages(
            prompt_messages, 
            model_id=model_id,
            enable_cache=enable_cache
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
            tool_config = self._convert_converse_tool_config(tools=tools)
            parameters["toolConfig"] = tool_config
            
            # Add cache point to tools if enabled and supported by the model
            if enable_cache and tool_config and "tools" in tool_config:
                # Check if model supports tool caching
                if cache_supported and "tools" in get_cache_config(model_id)["supported_fields"]:
                    # Add cache point after tools
                    if "cachePoint" not in tool_config:
                        tool_config["cachePoint"] = {"type": "default"}
                        print(f"[CACHE DEBUG] Added cache point to tools for model: {model_id}")
        
        # Print the full request parameters for debugging
        print(f"[CACHE DEBUG] Full request parameters: {json.dumps(parameters, default=str)}")
        logger.info(f"[CACHE DEBUG] Full request parameters: {json.dumps(parameters, default=str)}")
        try:
            # for issue #10976
            conversations_list = parameters["messages"]
            # if two consecutive user messages found, combine them into one message
            for i in range(len(conversations_list) - 2, -1, -1):
                if conversations_list[i]["role"] == conversations_list[i + 1]["role"]:
                    conversations_list[i]["content"].extend(conversations_list.pop(i + 1)["content"])
            logger.info(f"parameters: {parameters}")
            if stream:
                logger.info(f"stream: {stream}")
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
        logger.info(f"response: {response}")
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

                        # end of reasoningContent
                        elif "signature" in delta["reasoningContent"]: 
                            formatted_reasoning = '\n</think>'

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
                    if reasoning_header_added is False and full_assistant_content.startswith("<think>"):
                        assistant_prompt_message = AssistantPromptMessage(
                            content="\n</think>"
                        )
                        reasoning_header_added = True
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

        if "temperature" in model_parameters:
            inference_config["temperature"] = model_parameters["temperature"]

        if "top_p" in model_parameters:
            inference_config["topP"] = model_parameters["temperature"]

        if stop:
            inference_config["stopSequences"] = stop

        if "top_k" in model_parameters:
            additional_model_fields["top_k"] = model_parameters["top_k"]
            
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

    def _convert_converse_prompt_messages(self, prompt_messages: list[PromptMessage], model_id: str = None, enable_cache: bool = True) -> tuple[list, list[dict]]:
        """
        Convert prompt messages to dict list and system
        Add cache points for supported models when enable_cache is True
        
        :param prompt_messages: List of prompt messages to convert
        :param model_id: Model ID to check for cache support
        :param enable_cache: Whether to enable caching
        :return: Tuple of system messages and prompt message dicts
        """
        system = []
        prompt_message_dicts = []
        
        # Check if model supports caching
        cache_supported = model_id and is_cache_supported(model_id) and enable_cache
        cache_config = get_cache_config(model_id) if cache_supported else None
        
        # Process system messages first
        system_messages = [msg for msg in prompt_messages if isinstance(msg, SystemPromptMessage)]
        other_messages = [msg for msg in prompt_messages if not isinstance(msg, SystemPromptMessage)]
        
        # Add system messages
        for message in system_messages:
            message.content = message.content.strip()
            system.append({"text": message.content})
            
        # Add cache point to system if it's not empty and caching is supported for system field
        if system and cache_supported and cache_config and "system" in cache_config["supported_fields"]:
            system.append({"cachePoint": {"type": "default"}})
            print(f"[CACHE DEBUG] Added cache point to system messages for model: {model_id}")
            
        # Process other messages
        for message in other_messages:
            message_dict = self._convert_prompt_message_to_dict(message)
            prompt_message_dicts.append(message_dict)
            
        # Add cache point to the last message if caching is supported for messages field
        if prompt_message_dicts and cache_supported and cache_config and "messages" in cache_config["supported_fields"]:
            # For the last user message, add a cache point
            if prompt_message_dicts[-1]["role"] == "user":
                # Check if content is a list and has enough elements
                if isinstance(prompt_message_dicts[-1]["content"], list):
                    # Add cache point to the content array
                    prompt_message_dicts[-1]["content"].append({"cachePoint": {"type": "default"}})
                    print(f"[CACHE DEBUG] Added cache point to user message content list for model: {model_id}")
                else:
                    # If content is not a list, convert it to a list with the original content and add cache point
                    original_content = prompt_message_dicts[-1]["content"]
                    prompt_message_dicts[-1]["content"] = [{"text": original_content}, {"cachePoint": {"type": "default"}}]
                    print(f"[CACHE DEBUG] Converted user message content to list and added cache point for model: {model_id}")

        # Print the final system and messages for debugging
        print(f"[CACHE DEBUG] System messages: {json.dumps(system, default=str)}")
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
            if message.tool_calls:
                message_dict = {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": message.tool_calls[0].id,
                                "name": message.tool_calls[0].function.name,
                                "input": json.loads(message.tool_calls[0].function.arguments),
                            }
                        }
                    ],
                }
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
        prefix = model.split(".")[0]
        model_name = model.split(".")[1]

        if isinstance(prompt_messages, str):
            prompt = prompt_messages
        else:
            prompt = self._convert_messages_to_prompt(prompt_messages, prefix, model_name)

        return self._get_num_tokens_by_gpt2(prompt)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        required_params = {}
        if "anthropic" in model:
            required_params = {
                "max_tokens": 32,
            }
        elif "ai21" in model:
            # ValidationException: Malformed input request: #/temperature: expected type: Number,
            # found: Null#/maxTokens: expected type: Integer, found: Null#/topP: expected type: Number, found: Null,
            # please reformat your input and try again.
            required_params = {
                "temperature": 0.7,
                "topP": 0.9,
                "maxTokens": 32,
            }

        try:
            ping_message = UserPromptMessage(content="ping")
            self._invoke(
                model=model,
                credentials=credentials,
                prompt_messages=[ping_message],
                model_parameters=required_params,
                stream=False,
            )

        except ClientError as ex:
            error_code = ex.response["Error"]["Code"]
            full_error_msg = f"{error_code}: {ex.response['Error']['Message']}"
            raise CredentialsValidateFailedError(str(self._map_client_to_invoke_error(error_code, full_error_msg)))

        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

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

    def _convert_messages_to_anthropic_format(self, messages: list[PromptMessage], enable_cache: bool = False) -> list[dict]:
        """
        Convert messages to Anthropic format with cache_control if enabled
        
        :param messages: List of prompt messages
        :param enable_cache: Whether to enable caching
        :return: List of messages in Anthropic format
        """
        formatted_messages = []
        
        for message in messages:
            if isinstance(message, UserPromptMessage):
                if isinstance(message.content, str):
                    content = [{"type": "text", "text": message.content}]
                    
                    # Add cache_control to user messages if enabled
                    if enable_cache:
                        content.append({
                            "type": "text",
                            "text": "",
                            "cache_control": {"type": "ephemeral"}
                        })
                    
                    formatted_messages.append({
                        "role": "user",
                        "content": content
                    })
                else:
                    # Handle multi-modal content
                    content = []
                    for item in message.content:
                        if item.type == PromptMessageContentType.TEXT:
                            content.append({"type": "text", "text": item.data})
                        elif item.type == PromptMessageContentType.IMAGE:
                            # Process image data
                            data_split = item.data.split(";base64,")
                            mime_type = data_split[0].replace("data:", "")
                            base64_data = data_split[1]
                            
                            content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": base64_data
                                }
                            })
                    
                    # Add cache_control if enabled
                    if enable_cache:
                        content.append({
                            "type": "text",
                            "text": "",
                            "cache_control": {"type": "ephemeral"}
                        })
                    
                    formatted_messages.append({
                        "role": "user",
                        "content": content
                    })
            
            elif isinstance(message, AssistantPromptMessage):
                if message.tool_calls:
                    # Handle tool calls
                    formatted_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": message.content}],
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": tool_call.type,
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments
                                }
                            } for tool_call in message.tool_calls
                        ]
                    })
                else:
                    formatted_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": message.content}]
                    })
            
            elif isinstance(message, ToolPromptMessage):
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": [{"type": "text", "text": message.content}]
                })
        
        return formatted_messages

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
        model_prefix = model.split(".")[0]
        model_name = model.split(".")[1]

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
        # Extract enable_cache parameter, default to True
        enable_cache = model_parameters.pop("enable_cache", True)
        
        # Check if model supports caching
        cache_supported = is_cache_supported(model) and enable_cache
        
        client_config = Config(region_name=credentials["aws_region"])

        runtime_client = boto3.client(
            service_name="bedrock-runtime",
            config=client_config,
            aws_access_key_id=credentials.get("aws_access_key_id"),
            aws_secret_access_key=credentials.get("aws_secret_access_key"),
        )

        model_prefix = model.split(".")[0]
        model_name = model.split(".")[1] if len(model.split(".")) > 1 else ""
        
        # Create base payload
        payload = self._create_payload(model, prompt_messages, model_parameters, stop, stream)
        
        # Add cache points if supported
        if cache_supported:
            if model_prefix == "anthropic":
                # For Anthropic models using InvokeModel API
                if "messages" in payload:
                    # Use the new method to format messages with cache control
                    anthropic_messages = self._convert_messages_to_anthropic_format(prompt_messages, enable_cache=True)
                    payload["messages"] = anthropic_messages
                elif "prompt" in payload:
                    # For older Anthropic format
                    # Add cache control marker at the end of the prompt
                    cache_marker = "\n\nCache Control: ephemeral"
                    if not payload["prompt"].endswith(cache_marker):
                        payload["prompt"] += cache_marker
                        
                # Log that cache is enabled for this request
                logger.info(f"Cache enabled for Anthropic model: {model}")
            
            elif model_prefix == "amazon" and "nova" in model_name:
                # For Amazon Nova models
                if "messages" in payload:
                    for message in payload["messages"]:
                        if message["role"] == "user" and "content" in message:
                            if isinstance(message["content"], list):
                                message["content"].append({"cachePoint": {"type": "default"}})
                            else:
                                message["content"] = [
                                    {"text": message["content"]},
                                    {"cachePoint": {"type": "default"}}
                                ]
                
                if "system" in payload and isinstance(payload["system"], list):
                    payload["system"].append({"cachePoint": {"type": "default"}})
                elif "system" in payload and isinstance(payload["system"], str):
                    payload["system"] = [
                        {"text": payload["system"]},
                        {"cachePoint": {"type": "default"}}
                    ]
                    
                # Log that cache is enabled for this request
                logger.info(f"Cache enabled for Amazon Nova model: {model}")

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
        model_name = model.split(".")[1] if len(model.split(".")) > 1 else ""
        logger.info(f"model_prefix: {model_prefix}, model_name: {model_name}")
        if model_prefix == "ai21":
            output = response_body.get("completions")[0].get("data").get("text")
            prompt_tokens = len(response_body.get("prompt").get("tokens"))
            completion_tokens = len(response_body.get("completions")[0].get("data").get("tokens"))

        elif model_prefix == "anthropic":
            output = response_body.get("completion")
            prompt_tokens = response_body.get("usage", {}).get("input_tokens", 0)
            completion_tokens = response_body.get("usage", {}).get("output_tokens", 0)
            
            # Log cache metrics if available
            if "usage" in response_body:
                cache_read_tokens = response_body["usage"].get("cache_read_input_tokens", 0)
                cache_write_tokens = response_body["usage"].get("cache_write_input_tokens", 0)
                
                # Always log the metrics for debugging
                print(f"[ANTHROPIC CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                logger.info(f"[ANTHROPIC CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                
                # Print the full usage data for debugging
                print(f"[ANTHROPIC USAGE DATA] {json.dumps(response_body['usage'], default=str)}")
                
                if cache_read_tokens > 0 or cache_write_tokens > 0:
                    logger.info(f"Cache metrics - Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    if cache_read_tokens > 0:
                        print(f"[ANTHROPIC CACHE HIT] {cache_read_tokens} tokens read from cache")
                        logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
                    elif cache_write_tokens > 0:
                        print(f"[ANTHROPIC CACHE WRITE] {cache_write_tokens} tokens written to cache")
                        logger.info(f"Cache write detected - {cache_write_tokens} tokens written to cache")
        
        elif model_prefix == "amazon" and "nova" in model_name:
            output = response_body.get("output", {}).get("text", "")
            prompt_tokens = response_body.get("usage", {}).get("inputTokens", 0)
            completion_tokens = response_body.get("usage", {}).get("outputTokens", 0)
            
            # Log cache metrics if available
            if "usage" in response_body:
                cache_read_tokens = response_body["usage"].get("cacheReadInputTokens", 0)
                cache_write_tokens = response_body["usage"].get("cacheWriteInputTokens", 0)
                
                # Always log the metrics for debugging
                print(f"[NOVA CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                logger.info(f"[NOVA CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                
                # Print the full usage data for debugging
                print(f"[NOVA USAGE DATA] {json.dumps(response_body['usage'], default=str)}")
                
                if cache_read_tokens > 0 or cache_write_tokens > 0:
                    logger.info(f"Cache metrics - Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    if cache_read_tokens > 0:
                        print(f"[NOVA CACHE HIT] {cache_read_tokens} tokens read from cache")
                        logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
                    elif cache_write_tokens > 0:
                        print(f"[NOVA CACHE WRITE] {cache_write_tokens} tokens written to cache")
                        logger.info(f"Cache write detected - {cache_write_tokens} tokens written to cache")

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
        model_name = model.split(".")[1] if len(model.split(".")) > 1 else ""
        
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

            if model_prefix == "anthropic":
                content_delta = payload.get("completion")
                finish_reason = payload.get("stop_reason")
                
                # Extract cache metrics if available in the last chunk
                if finish_reason and "usage" in payload:
                    cache_read_tokens = payload["usage"].get("cache_read_input_tokens", 0)
                    cache_write_tokens = payload["usage"].get("cache_write_input_tokens", 0)
                    
                    # Always log the metrics for debugging
                    print(f"[ANTHROPIC STREAM CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    logger.info(f"[ANTHROPIC STREAM CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    
                    # Print the full usage data for debugging
                    print(f"[ANTHROPIC STREAM USAGE DATA] {json.dumps(payload['usage'], default=str)}")
                    
                    if cache_read_tokens > 0 or cache_write_tokens > 0:
                        logger.info(f"Cache metrics - Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                        if cache_read_tokens > 0:
                            print(f"[ANTHROPIC STREAM CACHE HIT] {cache_read_tokens} tokens read from cache")
                            logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
                        elif cache_write_tokens > 0:
                            print(f"[ANTHROPIC STREAM CACHE WRITE] {cache_write_tokens} tokens written to cache")
                            logger.info(f"Cache write detected - {cache_write_tokens} tokens written to cache")
            
            elif model_prefix == "amazon" and "nova" in model_name:
                content_delta = payload.get("output", {}).get("text", "")
                finish_reason = payload.get("stopReason")
                
                # Extract cache metrics if available in the last chunk
                if finish_reason and "usage" in payload:
                    cache_read_tokens = payload["usage"].get("cacheReadInputTokens", 0)
                    cache_write_tokens = payload["usage"].get("cacheWriteInputTokens", 0)
                    
                    # Always log the metrics for debugging
                    print(f"[NOVA STREAM CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    logger.info(f"[NOVA STREAM CACHE METRICS] Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                    
                    # Print the full usage data for debugging
                    print(f"[NOVA STREAM USAGE DATA] {json.dumps(payload['usage'], default=str)}")
                    
                    if cache_read_tokens > 0 or cache_write_tokens > 0:
                        logger.info(f"Cache metrics - Model: {model}, Read: {cache_read_tokens} tokens, Write: {cache_write_tokens} tokens")
                        if cache_read_tokens > 0:
                            print(f"[NOVA STREAM CACHE HIT] {cache_read_tokens} tokens read from cache")
                            logger.info(f"Cache hit detected - {cache_read_tokens} tokens read from cache")
                        elif cache_write_tokens > 0:
                            print(f"[NOVA STREAM CACHE WRITE] {cache_write_tokens} tokens written to cache")
                            logger.info(f"Cache write detected - {cache_write_tokens} tokens written to cache")
            
            elif model_prefix == "cohere":
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
                prompt_tokens = payload.get("amazon-bedrock-invocationMetrics", {}).get("inputTokenCount", 0)
                completion_tokens = payload.get("amazon-bedrock-invocationMetrics", {}).get("outputTokenCount", 0)

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

    def _convert_messages_to_anthropic_format(self, messages: list[PromptMessage], enable_cache: bool = False) -> list[dict]:
        """
        Convert messages to Anthropic format with cache_control if enabled
        
        :param messages: List of prompt messages
        :param enable_cache: Whether to enable caching
        :return: List of messages in Anthropic format
        """
        formatted_messages = []
        
        for message in messages:
            if isinstance(message, UserPromptMessage):
                if isinstance(message.content, str):
                    content = [{"type": "text", "text": message.content}]
                    
                    # Add cache_control to user messages if enabled
                    if enable_cache:
                        content.append({
                            "type": "text",
                            "text": "",
                            "cache_control": {"type": "ephemeral"}
                        })
                    
                    formatted_messages.append({
                        "role": "user",
                        "content": content
                    })
                else:
                    # Handle multi-modal content
                    content = []
                    for item in message.content:
                        if item.type == PromptMessageContentType.TEXT:
                            content.append({"type": "text", "text": item.data})
                        elif item.type == PromptMessageContentType.IMAGE:
                            # Process image data
                            data_split = item.data.split(";base64,")
                            mime_type = data_split[0].replace("data:", "")
                            base64_data = data_split[1]
                            
                            content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": base64_data
                                }
                            })
                    
                    # Add cache_control if enabled
                    if enable_cache:
                        content.append({
                            "type": "text",
                            "text": "",
                            "cache_control": {"type": "ephemeral"}
                        })
                    
                    formatted_messages.append({
                        "role": "user",
                        "content": content
                    })
            
            elif isinstance(message, AssistantPromptMessage):
                if message.tool_calls:
                    # Handle tool calls
                    formatted_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": message.content}],
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": tool_call.type,
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments
                                }
                            } for tool_call in message.tool_calls
                        ]
                    })
                else:
                    formatted_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": message.content}]
                    })
            
            elif isinstance(message, ToolPromptMessage):
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": [{"type": "text", "text": message.content}]
                })
        
        return formatted_messages
