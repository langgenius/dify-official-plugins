import os
import base64
import uuid
import json
import logging
import mimetypes
from collections.abc import Generator
from typing import Optional, Union
import requests
import oci
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
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
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from .call_api import patched_call_api
from utils.oci_private_key import normalize_private_key
from oci.base_client import BaseClient 
BaseClient.call_api = patched_call_api

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Cohere models that OCI only serves through the v2 chat format (CohereChatRequestV2,
# apiFormat COHEREV2). The remaining Cohere models keep using the v1 format below.
COHERE_V2_MODELS = {
    "cohere.command-a-vision",
}

class OCILargeLanguageModel(LargeLanguageModel):
    def _get_oci_credentials(self, credentials: dict) -> dict:
        if credentials.get("authentication_method") == "instance_principal_authentication":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            oci_credentials = {"config": {}, "signer": signer}
        elif credentials.get("authentication_method") == "api_key_authentication":
            if "key_content" not in credentials:
                raise CredentialsValidateFailedError("need to set key_content in credentials ")
            if "tenancy_ocid" not in credentials:
                raise CredentialsValidateFailedError("need to set tenancy_ocid in credentials ")
            if "user_ocid" not in credentials:
                raise CredentialsValidateFailedError("need to set user_ocid in credentials ")
            if "fingerprint" not in credentials:
                raise CredentialsValidateFailedError("need to set fingerprint in credentials ")
            if "default_region" not in credentials:
                raise CredentialsValidateFailedError("need to set default_region in credentials ")
            if "compartment_ocid" not in credentials:
                raise CredentialsValidateFailedError("need to set compartment_ocid in credentials ")

            key_content = normalize_private_key(credentials.get("key_content"))

            config = {
                "tenancy": credentials.get("tenancy_ocid"),
                "user": credentials.get("user_ocid"),
                "fingerprint": credentials.get("fingerprint"),
                "key_content": key_content,
                "region": credentials.get("default_region"),
                "pass_phrase": None
            }                
            
            oci.config.validate_config(config)
            oci_credentials = {"config": config}
        else:
            raise CredentialsValidateFailedError(
                f"unsupported authentication_method: {credentials.get('authentication_method')}"
            )
        return oci_credentials


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
        return self._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return:md = genai.GenerativeModel(model)
        """
        prompt = self._convert_messages_to_prompt(prompt_messages)
        return self._get_num_tokens_by_gpt2(prompt)

    def get_num_characters(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return:md = genai.GenerativeModel(model)
        """
        prompt = self._convert_messages_to_prompt(prompt_messages)
        return len(prompt)

    def _convert_messages_to_prompt(self, messages: list[PromptMessage]) -> str:
        """
        :param messages: List of PromptMessage to combine.
        :return: Combined string with necessary human_prompt and ai_prompt tags.
        """
        messages = messages.copy()
        text = "".join((self._convert_one_message_to_text(message) for message in messages))
        return text.rstrip()

    def validate_credentials(self, credentials: dict) -> None:
        """
        Validate model credentials through list model

        :param credentials: model credentials
        :return:
        """
        try:
            self._list_models(credentials,limit=1)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _list_models(self, credentials: dict, limit: int = None) -> list[str]:
        """
        List models

        :param credentials: model credentials
        :return: list of model names
        """
        oci_credentials = self._get_oci_credentials(credentials)
        generative_ai_client = oci.generative_ai.GenerativeAiClient(**oci_credentials)            
        list_models_response = generative_ai_client.list_models(
                    compartment_id=credentials.get("compartment_ocid"),
                    capability=["TEXT_GENERATION"],
                    limit = limit
                    )

        # Get the data from response
        return [model.display_name for model in list_models_response.data.items]
    
    def _generate(
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
        :param credentials: credentials kwargs
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        model_schema = self.get_model_schema(model=model)

        if model_parameters.get("frequency_penalty",0) > 0 and model_parameters.get("presence_penalty",0) > 0:
            raise InvokeBadRequestError("Cannot set both frequency penalty and presence penalty")

        
        if tools and model_schema is not None and model_schema.features is not None \
                and ModelFeature.TOOL_CALL not in model_schema.features:
            raise InvokeBadRequestError(f"{model} does not support function calling")

        oci_credentials = self._get_oci_credentials(credentials)
        client = oci.generative_ai_inference.GenerativeAiInferenceClient(**oci_credentials)

        vendor = model.split(".")[0].lower()

        compartment_id = credentials.get("compartment_ocid")
        serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(
                serving_type = "ON_DEMAND",
                model_id = model
                )

        chat_detail = oci.generative_ai_inference.models.ChatDetails(
            compartment_id=compartment_id,
            serving_mode=serving_mode
        )

        infer_params = {
            "is_stream": stream,
            "temperature": model_parameters.get("temperature"),
            "top_p": model_parameters.get("topP"),
            "max_tokens": model_parameters.get("maxTokens"),
            "frequency_penalty": model_parameters.get("frequencyPenalty"),
            "presence_penalty": model_parameters.get("presencePenalty"),
        }
        
        # Cohere model call, v2 chat format (Command A Vision only accepts this format)
        if vendor == "cohere" and model in COHERE_V2_MODELS:
            chat_request = oci.generative_ai_inference.models.CohereChatRequestV2(
                stop_sequences = stop,
                **infer_params
            )
            chat_request.messages = [
                Convertor()._parse_prompt_message_to_cohere_v2(message) for message in prompt_messages
            ]
            if tools:
                chat_request.tools = Convertor().convert_tools_to_cohere_v2(tools)

        # Cohere model call, v1 chat format
        elif vendor == "cohere":
            chat_request = oci.generative_ai_inference.models.CohereChatRequest(
                stop_sequences = stop,
                **infer_params
            ) 

            chat_history = []
            for idx, message in enumerate(prompt_messages, start=1):                
                if idx < len(prompt_messages):
                    message = Convertor()._parse_prompt_message_to_cohere(message)
                    chat_history.append(message)
                else:
                    if isinstance(message, ToolPromptMessage):
                        chat_request.tool_results = Convertor()._parse_prompt_message_to_cohere(message).tool_results
                        chat_request.message = ""
                    else:
                        chat_request.message = Convertor()._get_message_content_text(message.content)
            chat_request.chat_history = chat_history

            if tools:
                chat_request.tools = Convertor().convert_tools_to_cohere(tools)
        
        # Generic model call
        else:
            chat_request = oci.generative_ai_inference.models.GenericChatRequest(                
                stop = stop,
                **infer_params
            )
            oci_messages = []
            for message in prompt_messages:
                oci_messages.append(Convertor()._parse_prompt_message_to_generic(message))
            chat_request.messages = oci_messages

            if tools:
                chat_request.tools = Convertor().convert_tools_to_generic(tools)
        
        chat_detail.chat_request = chat_request
        body = client.base_client.sanitize_for_serialization(chat_detail) 
        
        if "isStream" in body["chatRequest"]:
            if body["chatRequest"]["isStream"]:
                body["chatRequest"]["streamOptions"] = {"isIncludeUsage": True}
        reasoning_effort = model_parameters.get("reasoningEffort") or model_parameters.get("reasoning_effort")
        if reasoning_effort:
            # OCI expects the camelCase key and an upper-case enum value (LOW / MEDIUM / HIGH);
            # "reasoning_effort" / lower-case values are rejected with HTTP 400.
            body["chatRequest"]["reasoningEffort"] = str(reasoning_effort).upper()
        body = json.dumps(body)
        logging.debug("Request body:  %s", body)
        
        response = client.base_client.call_api(
            resource_path="/actions/chat",
            method="POST",
            operation_name="chat",
            header_params={
                "accept": "application/json, text/event-stream",
                "content-type": "application/json"
            },
            body=body,
            #response_type="ChatResult"
            )
        if stream:
            return self._handle_generate_stream_response(model, credentials, response, prompt_messages)
        else:
            json_response = json.loads(response.data.text)
            return self._handle_generate_response(model, credentials, json_response, prompt_messages)

    def _handle_generate_response(
        self, 
        model: str,
        credentials: dict,
        response: oci.generative_ai_inference.models.BaseChatResponse,
        prompt_messages: list[PromptMessage]
    ) -> LLMResult:
        """
        Handle llm response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response
        """
        model_id = response.get("modelId") or model
        vendor = model_id.split(".")[0].lower()
        logging.debug("OCI Response:  %s", response)
        chat_response = response["chatResponse"]
        api_format = chat_response.get("apiFormat")
        assistant_prompt_message = AssistantPromptMessage(content = "")
        convertor = Convertor()

        # Cohere v2 response: {"message": {"content": [{"type": "TEXT", "text": ...}], "toolCalls": [...]}}
        if api_format == "COHEREV2":
            message = chat_response.get("message") or {}
            response_tool_calls = message.get("toolCalls")
            if response_tool_calls:
                assistant_prompt_message.tool_calls = convertor.convert_response_tool_calls(response_tool_calls, vendor)
            assistant_prompt_message.content = convertor._join_text_content(message.get("content"))
        # Cohere v1 response: {"text": ..., "toolCalls": [...]}
        elif vendor == "cohere":
            response_tool_calls = chat_response.get("toolCalls")
            if response_tool_calls:
                assistant_prompt_message.tool_calls = convertor.convert_response_tool_calls(response_tool_calls, vendor)
            else:
                assistant_prompt_message.content = chat_response.get("text") or ""
        # Generic response: {"choices": [{"message": {"content": [...], "toolCalls": [...]}, "finishReason": ...}]}
        else:
            choice = chat_response["choices"][0]
            message = choice.get("message") or {}
            response_tool_calls = message.get("toolCalls")
            if choice.get("finishReason") == "tool_calls" or response_tool_calls:
                assistant_prompt_message.tool_calls = convertor.convert_response_tool_calls(response_tool_calls or [], vendor)
            assistant_prompt_message.content = convertor._join_text_content(message.get("content"))

        usage_info = chat_response.get("usage") or response.get("usage") or {}
        prompt_tokens = int(usage_info.get("promptTokens") or 0)
        total_tokens = int(usage_info.get("totalTokens") or prompt_tokens)
        # total - prompt also covers reasoning tokens, which OCI bills as output.
        completion_tokens = max(total_tokens - prompt_tokens, 0)
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        result = LLMResult(model=model, prompt_messages=prompt_messages, message=assistant_prompt_message, usage=usage)
        logging.debug("OCI Response to Dify:  %s", result)
        return result

    def _handle_generate_stream_response(
        self, 
        model: str,
        credentials: dict,
        response,
        prompt_messages: list[PromptMessage]
    ) -> Generator:
            """
            Handle llm stream response

            Content deltas are yielded as they arrive. Tool calls are accumulated (some
            models, e.g. gpt-oss, stream the name once and then argument fragments) and
            emitted together with the finish reason and usage in a single terminal chunk.

            :param model: model name
            :param credentials: credentials
            :param response: response
            :param prompt_messages: prompt messages
            :return: llm response chunk generator result
            """
            index = -1
            vendor = model.split(".")[0].lower()
            # Cohere v1 streams {"text": ..., "toolCalls": ...}; Cohere v2 and the generic
            # format both stream {"message": {"content": [...], "toolCalls": [...]}}.
            cohere_v1_stream = vendor == "cohere" and model not in COHERE_V2_MODELS
            convertor = Convertor()
            finish_reason = None
            usage = None
            pending_tool_calls: list[dict] = []
            terminal_emitted = False

            def terminal_chunk() -> LLMResultChunk:
                message = AssistantPromptMessage(
                    content="",
                    tool_calls=convertor.build_tool_calls(pending_tool_calls),
                )
                return LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=message,
                        finish_reason=finish_reason,
                        usage=usage,
                    ),
                )

            for event in response.data.events():
                raw = event.data
                # Some models (e.g. Llama 4) terminate the SSE stream with a literal [DONE].
                if not raw or raw.strip() == "[DONE]":
                    continue
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    logging.debug("Skipping non-JSON stream event: %r", raw[:200])
                    continue
                if not isinstance(chunk, dict):
                    continue

                if "finishReason" not in chunk:
                    assistant_prompt_message = AssistantPromptMessage(content="")
                    if cohere_v1_stream:
                        if chunk.get("toolCalls"):
                            assistant_prompt_message.tool_calls = convertor.convert_response_tool_calls(chunk["toolCalls"], vendor)
                        elif chunk.get("text"):
                            assistant_prompt_message.content = chunk["text"]
                    else:
                        message = chunk.get("message") or {}
                        assistant_prompt_message.content = convertor._join_text_content(message.get("content"))
                        for tool_call in message.get("toolCalls") or []:
                            convertor.accumulate_tool_call_delta(pending_tool_calls, tool_call)

                    if assistant_prompt_message.content or assistant_prompt_message.tool_calls:
                        index += 1
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(index=index, message=assistant_prompt_message),
                        )

                if chunk.get("finishReason"):
                    finish_reason = str(chunk["finishReason"])
                    logging.debug("Stream finishReason:  %s", chunk)
                if chunk.get("usage"):
                    logging.debug("Stream usage:  %s", chunk)
                    prompt_tokens = int(chunk["usage"].get("promptTokens") or 0)
                    total_tokens = int(chunk["usage"].get("totalTokens") or prompt_tokens)
                    # total - prompt also covers reasoning tokens, which OCI bills as output.
                    usage = self._calc_response_usage(model, credentials, prompt_tokens, max(total_tokens - prompt_tokens, 0))

                if finish_reason and usage and not terminal_emitted:
                    terminal_emitted = True
                    yield terminal_chunk()

            if not terminal_emitted and (finish_reason or usage or pending_tool_calls):
                yield terminal_chunk()
            
    def _convert_one_message_to_text(self, message: PromptMessage) -> str:
        """
        Convert a single message to a string.

        :param message: PromptMessage to convert.
        :return: String representation of the message.
        """
        human_prompt = "\n\nuser:"
        ai_prompt = "\n\nmodel:"
        content = message.content
        if isinstance(content, list):
            content = "".join((c.data for c in content if c.type != PromptMessageContentType.IMAGE))
        if isinstance(message, UserPromptMessage):
            message_text = f"{human_prompt} {content}"
        elif isinstance(message, AssistantPromptMessage):
            message_text = f"{ai_prompt} {content}"
        elif isinstance(message, SystemPromptMessage | ToolPromptMessage):
            message_text = f"{human_prompt} {content}"
        else:
            raise ValueError(f"Got unknown type {message}")
        return message_text

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [],
            InvokeServerUnavailableError: [],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [],
        }

        

class Convertor:
    def __init__(self):        
        self.type_mapping = {
            "array": "list",
            "boolean": "bool",
            "null": "NoneType",
            "integer": "int",
            "number": "float",
            "object": "dict",
            "regular expressions": "str",
            "string": "str"
        }

    def _get_message_content_text(self, content) :
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = ""
            images = []
            for c in content:
                if c.type == PromptMessageContentType.TEXT:
                    text += "\n"+c.data
                elif c.type == PromptMessageContentType.IMAGE:
                    images.append(c.data)                        
        else:
            raise ValueError(f"Got unknown message content type {type(content)}")
        return text

    @staticmethod
    def _join_text_content(content) -> str:
        """
        Join the TEXT parts of an OCI content list ([{"type": "TEXT", "text": ...}, ...]).
        Tolerates a missing / empty list and non-text parts.
        """
        if not content:
            return ""
        if isinstance(content, str):
            return content
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("text") and part.get("type", "TEXT") == "TEXT":
                parts.append(part["text"])
        return "".join(parts)

    ## convert prompt message to cohere v2 message
    def _parse_prompt_message_to_cohere_v2(self, message: PromptMessage):
        models = oci.generative_ai_inference.models
        content = []
        if isinstance(message.content, str):
            if message.content:
                content.append(models.CohereTextContentV2(text = message.content))
        elif isinstance(message.content, list):
            for c in message.content:
                if c.type == PromptMessageContentType.TEXT:
                    content.append(models.CohereTextContentV2(text = c.data))
                elif c.type == PromptMessageContentType.IMAGE:
                    image_url = self._process_image_url(c.data)
                    content.append(
                        models.CohereImageContentV2(image_url = models.CohereImageUrlV2(url = image_url))
                    )

        if isinstance(message, SystemPromptMessage):
            return models.CohereSystemMessageV2(content = content)
        if isinstance(message, UserPromptMessage):
            return models.CohereUserMessageV2(content = content)
        if isinstance(message, ToolPromptMessage):
            return models.CohereToolMessageV2(
                tool_call_id = message.tool_call_id or message.name,
                content = content or [models.CohereTextContentV2(text = "")],
            )
        if isinstance(message, AssistantPromptMessage):
            oci_message = models.CohereAssistantMessageV2(content = content or None)
            if message.tool_calls:
                oci_message.tool_calls = [
                    models.CohereToolCallV2(
                        id = tool.id or tool.function.name,
                        type = "FUNCTION",
                        function = {"name": tool.function.name, "arguments": tool.function.arguments},
                    )
                    for tool in message.tool_calls
                ]
            return oci_message
        raise ValueError(f"Got unknown message type {message}")

    def convert_tools_to_cohere_v2(self, tools: list) -> list:
        """
        Convert Dify tool definitions into OCI Cohere v2 tool objects (JSON-schema parameters).
        """
        models = oci.generative_ai_inference.models
        return [
            models.CohereToolV2(
                type = "FUNCTION",
                function = models.Function(
                    name = tool.name,
                    description = tool.description,
                    parameters = tool.parameters,
                ),
            )
            for tool in tools
        ]

    ## convert prompt message to cohere message
    def _parse_prompt_message_to_cohere(self,message: PromptMessage) :
        text = self._get_message_content_text(message.content)
        if isinstance(message, SystemPromptMessage):
            oci_message = oci.generative_ai_inference.models.CohereSystemMessage(
                message = text
            )
        elif isinstance(message, UserPromptMessage):
            oci_message = oci.generative_ai_inference.models.CohereUserMessage(
                message = text
            )
        
        elif isinstance(message, ToolPromptMessage):
            oci_message = oci.generative_ai_inference.models.CohereToolMessage(
                tool_results = [
                    oci.generative_ai_inference.models.CohereToolResult(
                        call = oci.generative_ai_inference.models.CohereToolCall(
                                name = message.tool_call_id,
                                parameters = {}
                            ),
                        outputs = [{"tool_results": text}]
                    )
                ]
            )
            
        elif isinstance(message, AssistantPromptMessage):
            oci_message = oci.generative_ai_inference.models.CohereChatBotMessage(
                message = text
            )
            if message.tool_calls:
                oci_tool_calls = []
                for tool in message.tool_calls:
                    oci_tool_calls.append(
                        oci.generative_ai_inference.models.CohereToolCall(
                            name = tool.function.name,
                            parameters = json.loads(tool.function.arguments)
                        )
                    )
                oci_message.tool_calls = oci_tool_calls          
        else:
            raise ValueError(f"Got unknown message type {message}")        
        return oci_message 

    ## convert prompt message to generic message
    def _parse_prompt_message_to_generic(self,message: PromptMessage) :
        content = []
        if isinstance(message.content, str):
            content.append(
                oci.generative_ai_inference.models.TextContent(text = message.content)
            )
        elif isinstance(message.content, list):
            for c in message.content:
                if c.type == PromptMessageContentType.TEXT:
                    content.append(
                        oci.generative_ai_inference.models.TextContent(text = c.data)
                    )
                elif c.type == PromptMessageContentType.IMAGE:
                    image_url = self._process_image_url(c.data)
                    image_url = oci.generative_ai_inference.models.ImageUrl(url = image_url)                    
                    content.append(
                        oci.generative_ai_inference.models.ImageContent(image_url = image_url)
                    )

        if isinstance(message, SystemPromptMessage):
            oci_message = oci.generative_ai_inference.models.SystemMessage(
                content = content
            )
        elif isinstance(message, UserPromptMessage):
            oci_message = oci.generative_ai_inference.models.UserMessage(
                content = content
            )
        
        elif isinstance(message, ToolPromptMessage):
            oci_message = oci.generative_ai_inference.models.ToolMessage(
                tool_call_id =  message.name,
                content = content
            )
        elif isinstance(message, AssistantPromptMessage):
            oci_message = oci.generative_ai_inference.models.AssistantMessage(
                content = content
            )
            if message.tool_calls:
                oci_tool_calls = []
                for tool in message.tool_calls:
                    oci_tool_calls.append(
                        oci.generative_ai_inference.models.FunctionCall(
                            type = "FUNCTION",
                            id = tool.function.name,
                            name = tool.function.name,
                            arguments = tool.function.arguments
                        )
                    )
                oci_message.tool_calls = oci_tool_calls   
                    
        else:
            raise ValueError(f"Got unknown message type {message}")        
        return oci_message

    def convert_tools_to_cohere(self, tools: list) -> list[oci.generative_ai_inference.models.CohereTool]:
        """
        Convert a list of Dify tool definitions into OCI Cohere tool objects.
        """
        cohere_tools = []    
        
        for tool in tools:
            name = tool.name.replace("-","_")
            description = tool.description
            parameters_schema = tool.parameters
                
            properties = parameters_schema.get("properties", {})
            required = parameters_schema.get("required", [])

            # Iterate through each property to build parameter definitions
            parameter_definitions = {}
            for param_name, param_schema in properties.items():
                is_required = param_name in required
                # Map the OpenAI JSON schema type to the Python type using type_mapping
                openai_type = param_schema.get("type", "string")
                mapped_type = self.type_mapping.get(openai_type, "str")
                param_description = param_schema.get("description", "")
                parameter_definitions[param_name] = oci.generative_ai_inference.models.CohereParameterDefinition(
                    is_required = is_required,
                    type = mapped_type,
                    description = param_description
                    )
            
            cohere_tool = oci.generative_ai_inference.models.CohereTool(
                name = name,
                description = description,
                parameter_definitions = parameter_definitions
                )
            cohere_tools.append(cohere_tool)
        
        return cohere_tools

    def convert_tools_to_generic(self, tools: list) -> list[oci.generative_ai_inference.models.FunctionDefinition]:
        """
        Convert a list of OpenAI tool definitions into OCI Generic tool objects.
        """
        generic_tools = []
        for tool in tools:
            generic_tool = oci.generative_ai_inference.models.FunctionDefinition(
                type = "FUNCTION",
                name = tool.name,
                description = tool.description,
                parameters = tool.parameters
            )
            generic_tools.append(generic_tool)     
        return generic_tools

    @staticmethod
    def accumulate_tool_call_delta(pending: list[dict], tool_call: dict) -> None:
        """
        Merge one streamed tool-call delta into ``pending``.

        Generic (gpt-oss) and Cohere v2 streams send the id/name in the first fragment and
        then argument fragments without a name; Grok / Llama send complete calls.
        """
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else tool_call
        name = function.get("name")
        arguments = function.get("arguments")
        if arguments is None and "parameters" in tool_call:
            arguments = json.dumps(tool_call["parameters"])
        if arguments is not None and not isinstance(arguments, str):
            arguments = json.dumps(arguments)

        if name or not pending:
            pending.append({"id": tool_call.get("id") or name or "", "name": name or "", "arguments": arguments or ""})
        else:
            pending[-1]["arguments"] += arguments or ""
            if tool_call.get("id") and not pending[-1]["id"]:
                pending[-1]["id"] = tool_call["id"]

    @staticmethod
    def build_tool_calls(pending: list[dict]) -> list[AssistantPromptMessage.ToolCall]:
        return [
            AssistantPromptMessage.ToolCall(
                id=call["id"] or call["name"],
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=call["name"],
                    arguments=call["arguments"] or "{}",
                ),
            )
            for call in pending
            if call["name"]
        ]

    # Convert OCI response tool calls to Dify tool calls
    def convert_response_tool_calls(self, tool_calls: list, vendor: str) -> list[AssistantPromptMessage.ToolCall]:
        """
        Convert a list of cohere tool calls into a list of Dify tool calls.        
        Returns: list: List of Dify tool call dictionaries.
        """
        dify_tool_calls = []
        for call in tool_calls:  
            # Cohere v2 and OpenAI-style payloads nest name/arguments under "function".
            function = call.get("function") if isinstance(call.get("function"), dict) else call
            name = function["name"]
            if "parameters" in call and "arguments" not in function:
                # Cohere v1: {"name": ..., "parameters": {...}}
                arguments = json.dumps(call["parameters"])
            else:
                arguments = function.get("arguments") or "{}"
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments)
            
            dify_call = AssistantPromptMessage.ToolCall(
                id = call.get("id") or name,
                type = "function",
                function = AssistantPromptMessage.ToolCall.ToolCallFunction  (
                    name = name,
                    arguments = arguments
                    )
                )
            dify_tool_calls.append(dify_call)
        return dify_tool_calls

    
    def _process_image_url(self, image_url: str) -> str:
        try:
            if image_url.startswith("http"):
                resp = requests.get(image_url)
                resp.raise_for_status()
                mime_type = (
                    resp.headers.get("Content-Type")
                    or mimetypes.guess_type(image_url)[0]
                    or "image/png"
                )
                img_bytes = resp.content
            elif os.path.exists(image_url):
                with open(image_url, "rb") as f:
                    img_bytes = f.read()
                mime_type = mimetypes.guess_type(image_url)[0] or "image/png"
            else:
                return image_url
            base64_data = base64.b64encode(img_bytes).decode("utf-8")
            img_url = f"data:{mime_type};base64,{base64_data}"
            return img_url
        except Exception as exc:
            raise InvokeBadRequestError(f"Failed to load image: {exc}")