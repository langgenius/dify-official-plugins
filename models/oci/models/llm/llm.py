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
from oci.base_client import BaseClient 
BaseClient.call_api = patched_call_api

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

            pem_prefix = '-----BEGIN RSA PRIVATE KEY-----\n'
            pem_suffix = '\n-----END RSA PRIVATE KEY-----'
            key_string = credentials.get("key_content")
            for part in key_string.split("-"):
                if len(part.strip()) > 64:
                    key_b64 = part.strip()
            key_content = pem_prefix + "\n".join(key_b64.split(" "))+ pem_suffix
            
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

        
        if "tool-call" in model_schema.features and tools is not None and len(tools) > 0:
            raise InvokeBadRequestError("Does not support function calling")        

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
        
        # Cohere model call
        if vendor == "cohere":
            chat_request = oci.generative_ai_inference.models.CohereChatRequest(
                stop_sequences = stop,
                **infer_params
            ) 

            converter = Convertor()
            history_end = len(prompt_messages) - 1
            if isinstance(prompt_messages[-1], ToolPromptMessage):
                while history_end > 0 and isinstance(prompt_messages[history_end - 1], ToolPromptMessage):
                    history_end -= 1
            chat_request.chat_history = [
                converter._parse_prompt_message_to_cohere(message)
                for message in prompt_messages[:history_end]
            ]
            if isinstance(prompt_messages[-1], ToolPromptMessage):
                chat_request.tool_results = [
                    result
                    for message in prompt_messages[history_end:]
                    for result in converter._parse_prompt_message_to_cohere(message).tool_results
                ]
                chat_request.message = ""
            else:
                chat_request.message = converter._get_message_content_text(prompt_messages[-1].content)

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
        if model_parameters.get("reasoning_effort"):
            body["chatRequest"]["reasoning_effort"] = model_parameters.get("reasoning_effort")
        body = json.dumps(body)
        logging.debug("Request body:  "+body)
        
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
        model_id = response["modelId"]
        vendor = model_id.split(".")[0].lower()        
        chat_response = response["chatResponse"]
        assistant_prompt_message = AssistantPromptMessage(content = "")
        # Cohere response
        if vendor == "cohere":
            finish_reason = chat_response.get("finishReason")
            response_tool_calls = chat_response.get("toolCalls")
            if response_tool_calls:
                tool_calls = Convertor().convert_response_tool_calls(response_tool_calls,vendor)
                assistant_prompt_message.tool_calls = tool_calls
            else:
                assistant_prompt_message.content = chat_response["text"]
        # Generic response
        else:
            choice = chat_response["choices"][0]
            finish_reason = choice["finishReason"]
            response_tool_calls = choice["message"].get("toolCalls")
            assistant_prompt_message = AssistantPromptMessage()
            if finish_reason == "tool_calls" or response_tool_calls:
                assistant_prompt_message.tool_calls = Convertor().convert_response_tool_calls(response_tool_calls,vendor)
            else:
                assistant_prompt_message.content = choice["message"]["content"][0]["text"]
        
        self._validate_tool_calls(assistant_prompt_message.tool_calls, finish_reason, vendor)
        prompt_tokens = chat_response["usage"]["promptTokens"]
        total_tokens = chat_response["usage"]["totalTokens"]
        completion_tokens = total_tokens - prompt_tokens
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        result = LLMResult(model=model, prompt_messages=prompt_messages, message=assistant_prompt_message, usage=usage)
        return result

    def _handle_generate_stream_response(
        self, 
        model: str,
        credentials: dict,
        response,
        prompt_messages: list[PromptMessage]
    ) -> Generator:
        """Collect native tool fragments before exposing complete calls to Dify."""
        index = 0
        vendor = model.split(".")[0].lower()
        finish_reason = None
        usage = None
        tool_calls = []
        calls_by_id = {}
        active_calls = {}
        try:
            for stream in response.data.events():
                chunk = json.loads(stream.data)
                if vendor == "cohere":
                    tool_calls.extend(Convertor().convert_response_tool_calls(chunk.get("toolCalls") or [], vendor))
                    text = chunk.get("text") or ""
                else:
                    message = chunk.get("message") or {}
                    text = "".join(part.get("text") or "" for part in message.get("content") or [])
                    for position, part in enumerate(message.get("toolCalls") or []):
                        call_id = part.get("id")
                        call = calls_by_id.get(call_id) if call_id else active_calls.get(position)
                        if call is None:
                            call = AssistantPromptMessage.ToolCall(
                                id=call_id or str(uuid.uuid4()),
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(name="", arguments=""),
                            )
                            tool_calls.append(call)
                            calls_by_id[call.id] = call
                        # OCI reuses array positions when the next call starts.
                        active_calls[position] = call
                        if part.get("name"):
                            call.function.name = part["name"]
                        call.function.arguments += part.get("arguments") or ""

                if text:
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(index=index, message=AssistantPromptMessage(content=text)),
                    )
                    index += 1
                if chunk.get("finishReason"):
                    finish_reason = chunk["finishReason"]
                if chunk.get("usage") is not None:
                    prompt_tokens = chunk["usage"]["promptTokens"]
                    completion_tokens = chunk["usage"]["totalTokens"] - prompt_tokens
                    usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        except Exception as error:
            raise self._transform_invoke_error(error) from error

        self._validate_tool_calls(tool_calls, finish_reason, vendor)
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content="", tool_calls=tool_calls),
                finish_reason=finish_reason,
                usage=usage,
            ),
        )
            
    @staticmethod
    def _validate_tool_calls(tool_calls, finish_reason, vendor: str) -> None:
        successful_reasons = ("COMPLETE",) if vendor == "cohere" else ("stop", "tool_calls")
        for call in tool_calls:
            if finish_reason not in successful_reasons:
                raise InvokeError("The model stopped before completing its tool calls.")
            if not call.function.name or not call.function.name.strip():
                raise InvokeError("The model returned a tool call without a function name.")
            try:
                parameters = json.loads(call.function.arguments)
            except (TypeError, ValueError) as error:
                raise InvokeError("The model returned invalid tool arguments.") from error
            if not isinstance(parameters, dict):
                raise InvokeError("Tool arguments must be a JSON object.")

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
        self.tool_calls: dict[str, AssistantPromptMessage.ToolCall] = {}
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
        if content is None:
            return ""
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
            raise ValueError(f"Got unknown message content {content}")
        return text

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
            call = self.tool_calls.get(message.tool_call_id)
            if call is None:
                raise ValueError(f"Unknown tool call ID: {message.tool_call_id}")
            oci_message = oci.generative_ai_inference.models.CohereToolMessage(
                tool_results = [
                    oci.generative_ai_inference.models.CohereToolResult(
                        call = oci.generative_ai_inference.models.CohereToolCall(
                                name = call.function.name,
                                parameters = json.loads(call.function.arguments)
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
                    self.tool_calls[tool.id] = tool
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
                tool_call_id = message.tool_call_id,
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
                            id = tool.id,
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

    # Convert OCI response tool calls to Dify tool calls
    def convert_response_tool_calls(self, tool_calls: list, vendor: str) -> list[AssistantPromptMessage.ToolCall]:
        """
        Convert a list of cohere tool calls into a list of Dify tool calls.        
        Returns: list: List of Dify tool call dictionaries.
        """
        dify_tool_calls = []
        for call in tool_calls:  
            name = call.get("name") or ""
            if vendor == "cohere":
                arguments = json.dumps(call.get("parameters"))
            else:
                arguments = call.get("arguments") or ""
            
            dify_call = AssistantPromptMessage.ToolCall(
                id = call.get("id") or str(uuid.uuid4()),
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
