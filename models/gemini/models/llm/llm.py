import base64
import tempfile
import json
import time
import os
from collections.abc import Generator
from typing import Optional, Union

import requests
import google.ai.generativelanguage as glm
import google.genai as genai
from google.api_core import exceptions
from google.genai.types import File, GenerateContentConfig,Tool, GoogleSearch, Part, Content,FunctionDeclaration
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageRole,
    PromptMessage,
    MultiModalPromptMessageContent,
    PromptMessageContentType,
    PromptMessageTool,
    PromptMessageContent,
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

from .utils import FileCache
from typing import Optional


file_cache = FileCache()

class GoogleLargeLanguageModel(LargeLanguageModel):
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

    def _convert_messages_to_prompt(self, messages: list[PromptMessage]) -> str:
        """
        Format a list of messages into a full prompt for the Google model

        :param messages: List of PromptMessage to combine.
        :return: Combined string with necessary human_prompt and ai_prompt tags.
        """
        messages = messages.copy()
        text = "".join((self._convert_one_message_to_text(message) for message in messages))
        return text.rstrip()
    def _convert_tools_to_glm_tool(self, tools: list[PromptMessageTool]) -> glm.Tool:
        """
        Convert tool messages to glm tools

        :param tools: tool messages
        :return: glm tools
        """
        function_declarations = []
        for tool in tools:
            properties = {}
            for key, value in tool.parameters.get("properties", {}).items():
                properties[key] = {
                    "type_": glm.Type.STRING,
                    "description": value.get("description", ""),
                    "enum": value.get("enum", []),
                }
            if properties:
                parameters = glm.Schema(
                    type=glm.Type.OBJECT, properties=properties, required=tool.parameters.get("required", [])
                )
            else:
                parameters = None
            function_declaration = glm.FunctionDeclaration(
                name=tool.name, parameters=parameters, description=tool.description
            )
            function_declarations.append(function_declaration)
        return glm.Tool(function_declarations=function_declarations)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            ping_message = UserPromptMessage(content="ping")
            self._generate(model, credentials, [ping_message], stream=False, model_parameters={"max_output_tokens": 5})
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

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
        config = GenerateContentConfig()
        if schema := model_parameters.get("schema"):
            try:
                schema = json.loads(schema)
            except:
                raise exceptions.InvalidArgument("Invalid JSON Schema")
            if tools:
                raise exceptions.InvalidArgument("gemini not support use Tools and JSON Schema at same time")
            config.response_schema = schema
            config.response_mime_type = "application/json"
        if stop:
            config.stop_sequences = stop
        if model_parameters.get("grounding"):
            config.tools = [Tool(google_search=GoogleSearch())]
        config.top_p = model_parameters.get("top_p", None)
        config.top_k = model_parameters.get("top_k", None)
        config.temperature = model_parameters.get("temperature", None)
        config.max_output_tokens = model_parameters.get("max_output_tokens", None)
        config.system_instruction = model_parameters.get("system_instruction", None)
        functions: list[FunctionDeclaration] = [Tool(google_search=GoogleSearch())] if model_parameters.get("grounding") else []
        for tool in tools or []:
            functions.append(FunctionDeclaration(name=tool.name, description=tool.description,parameters=tool.parameters))
            pass
        contents: list[Content] = []
        for msg in prompt_messages:
            if msg.role == PromptMessageRole.SYSTEM:
                config.system_instruction = msg.content
            elif msg.role == PromptMessageRole.ASSISTANT:
                contents.append({"role": PromptMessageRole.ASSISTANT, "parts": [Part.from_text(text=msg.content)]})
            elif msg.role == PromptMessageRole.USER:
                if isinstance(msg.content, list) and all(isinstance(item, PromptMessageContent) for item in msg.content):
                    for c in msg.content:
                        if c.type == PromptMessageContentType.TEXT:
                            contents.append(Part.from_text(text=c.data))
                        if c.type in [PromptMessageContentType.IMAGE, PromptMessageContentType.VIDEO, PromptMessageContentType.AUDIO, PromptMessageContentType.DOCUMENT]:
                            file = self._upload_file_content_to_google(c, credentials)
                            contents.append(file)
                elif isinstance(msg.content, str):
                    contents.append(Part.from_text(text=msg.content))
                else:
                    raise ValueError(f"Got unknown type {msg}")
            else:
                raise ValueError(f"Got unknown type {msg}")

        client = genai.Client(api_key=credentials["google_api_key"])
        if not contents:
            raise InvokeError("The user prompt message is required. You only add a system prompt message.")
        index = 0
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            index += 1
            assistant_prompt_message = AssistantPromptMessage(content="")
            if chunk.text:
                assistant_prompt_message.content += chunk.text
            if chunk.function_calls:
                assistant_prompt_message.tool_calls = [
                        AssistantPromptMessage.ToolCall(
                            id=chunk.function_calls.name,
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name=chunk.function_calls.name,
                                arguments=json.dumps(dict(chunk.function_calls.args.items())),
                            ),
                        )
                    ]
            if chunk.usage_metadata:
                prompt_tokens = chunk.usage_metadata.prompt_token_count
                completion_tokens = chunk.usage_metadata.candidates_token_count
            else:
                prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
                completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])
            if chunk.candidates[0].finish_reason:
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(index=index, message=assistant_prompt_message,finish_reason=chunk.candidates[0].finish_reason,usage=self._calc_response_usage(model,credentials,prompt_tokens,completion_tokens)),
                )
                return
            yield LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(index=index, message=assistant_prompt_message),
                )

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

    def _upload_file_content_to_google(self, message_content: MultiModalPromptMessageContent,credentials:dict) -> File:
        client = genai.Client(api_key=credentials["google_api_key"])

        key = f"{message_content.type.value}:{hash(message_content.data)}"
        if file_cache.exists(key):
            try:
                return genai.get_file(file_cache.get(key))
            except:
                pass
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            if message_content.base64_data:
                file_content = base64.b64decode(message_content.base64_data)
                temp_file.write(file_content)
            else:
                try:
                    response = requests.get(message_content.url)
                    response.raise_for_status()
                    temp_file.write(response.content)
                except Exception as ex:
                    raise ValueError(f"Failed to fetch data from url {message_content.url}, {ex}")
            temp_file.flush()
        file = client.files.upload(file=temp_file.name, config={"mime_type": message_content.mime_type})
        while file.state.name == "PROCESSING":
            time.sleep(5)
            file = client.files.get(file.name)
        # google will delete your upload files in 2 days.
        file_cache.setex(key, 47 * 60 * 60, file.name)

        try:
            os.unlink(temp_file.name)
        except PermissionError:
            # windows may raise permission error
            pass
        print("file uploaded", file.download_uri,file.mime_type,file.state.name)
        return file

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
            InvokeConnectionError: [exceptions.RetryError],
            InvokeServerUnavailableError: [
                exceptions.ServiceUnavailable,
                exceptions.InternalServerError,
                exceptions.BadGateway,
                exceptions.GatewayTimeout,
                exceptions.DeadlineExceeded,
            ],
            InvokeRateLimitError: [exceptions.ResourceExhausted, exceptions.TooManyRequests],
            InvokeAuthorizationError: [
                exceptions.Unauthenticated,
                exceptions.PermissionDenied,
                exceptions.Unauthenticated,
                exceptions.Forbidden,
            ],
            InvokeBadRequestError: [
                exceptions.BadRequest,
                exceptions.InvalidArgument,
                exceptions.FailedPrecondition,
                exceptions.OutOfRange,
                exceptions.NotFound,
                exceptions.MethodNotAllowed,
                exceptions.Conflict,
                exceptions.AlreadyExists,
                exceptions.Aborted,
                exceptions.LengthRequired,
                exceptions.PreconditionFailed,
                exceptions.RequestRangeNotSatisfiable,
                exceptions.Cancelled,
            ],
        }
