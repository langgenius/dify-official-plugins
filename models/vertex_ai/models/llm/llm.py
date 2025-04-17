import base64
import io
import json
import time
from collections.abc import Generator
from typing import Optional, Union, cast
import google.auth.transport.requests
import requests
import vertexai.generative_models as glm
from anthropic import AnthropicVertex, Stream
from anthropic.types import (
    ContentBlockDeltaEvent,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    MessageStreamEvent,
)
from dify_plugin.entities.model import PriceType
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
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
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from google.api_core import exceptions
from google.cloud import aiplatform
from google.oauth2 import service_account
from PIL import Image


class VertexAiLargeLanguageModel(LargeLanguageModel):
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
        if "claude" in model:
            return self._generate_anthropic(model, credentials, prompt_messages, model_parameters, stop, stream, user)
        return self._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def _generate_anthropic(
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
        Invoke Anthropic large language model

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :return: full response or stream response chunk generator result
        """
        service_account_info = (
            json.loads(base64.b64decode(service_account_key))
            if (
                service_account_key := credentials.get("vertex_service_account_key", "")
            )
            else None
        )
        project_id = credentials["vertex_project_id"]
        SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
        token = ""
        if service_account_info:
            credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            token = credentials.token
        if "opus" in model or "claude-3-5-sonnet" in model:
            location = "us-east5"
        else:
            location = "us-central1"
        if token:
            client = AnthropicVertex(region=location, project_id=project_id, access_token=token)
        else:
            client = AnthropicVertex(region=location, project_id=project_id)
        extra_model_kwargs = {}
        if stop:
            extra_model_kwargs["stop_sequences"] = stop
        (system, prompt_message_dicts) = self._convert_claude_prompt_messages(prompt_messages)
        if system:
            extra_model_kwargs["system"] = system
        response = client.messages.create(
            model=model, messages=prompt_message_dicts, stream=stream, **model_parameters, **extra_model_kwargs
        )
        if stream:
            return self._handle_claude_stream_response(model, credentials, response, prompt_messages)
        return self._handle_claude_response(model, credentials, response, prompt_messages)

    def _handle_claude_response(
        self, model: str, credentials: dict, response: Message, prompt_messages: list[PromptMessage]
    ) -> LLMResult:
        """
        Handle llm chat response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: full response chunk generator result
        """
        assistant_prompt_message = AssistantPromptMessage(content=response.content[0].text)
        if response.usage:
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
        else:
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
            completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        response = LLMResult(
            model=response.model, prompt_messages=prompt_messages, message=assistant_prompt_message, usage=usage
        )
        return response

    def _handle_claude_stream_response(
        self, model: str, credentials: dict, response: Stream[MessageStreamEvent], prompt_messages: list[PromptMessage]
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
            for chunk in response:
                if isinstance(chunk, MessageStartEvent):
                    return_model = chunk.message.model
                    input_tokens = chunk.message.usage.input_tokens
                elif isinstance(chunk, MessageDeltaEvent):
                    output_tokens = chunk.usage.output_tokens
                    finish_reason = chunk.delta.stop_reason
                elif isinstance(chunk, MessageStopEvent):
                    usage = self._calc_response_usage(model, credentials, input_tokens, output_tokens)
                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=index + 1,
                            message=AssistantPromptMessage(content=""),
                            finish_reason=finish_reason,
                            usage=usage,
                        ),
                    )
                elif isinstance(chunk, ContentBlockDeltaEvent):
                    chunk_text = chunk.delta.text or ""
                    full_assistant_content += chunk_text
                    assistant_prompt_message = AssistantPromptMessage(content=chunk_text or "")
                    index = chunk.index
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(index=index, message=assistant_prompt_message),
                    )
        except Exception as ex:
            raise InvokeError(str(ex))

    def _calc_claude_response_usage(
        self, model: str, credentials: dict, prompt_tokens: int, completion_tokens: int
    ) -> LLMUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param prompt_tokens: prompt tokens
        :param completion_tokens: completion tokens
        :return: usage
        """
        prompt_price_info = self.get_price(
            model=model, credentials=credentials, price_type=PriceType.INPUT, tokens=prompt_tokens
        )
        completion_price_info = self.get_price(
            model=model, credentials=credentials, price_type=PriceType.OUTPUT, tokens=completion_tokens
        )
        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            prompt_unit_price=prompt_price_info.unit_price,
            prompt_price_unit=prompt_price_info.unit,
            prompt_price=prompt_price_info.total_amount,
            completion_tokens=completion_tokens,
            completion_unit_price=completion_price_info.unit_price,
            completion_price_unit=completion_price_info.unit,
            completion_price=completion_price_info.total_amount,
            total_tokens=prompt_tokens + completion_tokens,
            total_price=prompt_price_info.total_amount + completion_price_info.total_amount,
            currency=prompt_price_info.currency,
            latency=time.perf_counter() - self.started_at,
        )
        return usage

    def _convert_claude_prompt_messages(self, prompt_messages: list[PromptMessage]) -> tuple[str, list[dict]]:
        """
        Convert prompt messages to dict list and system
        """
        system = ""
        first_loop = True
        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                message.content = message.content.strip()
                if first_loop:
                    system = message.content
                    first_loop = False
                else:
                    system += "\n"
                    system += message.content
        prompt_message_dicts = []
        for message in prompt_messages:
            if not isinstance(message, SystemPromptMessage):
                prompt_message_dicts.append(self._convert_claude_prompt_message_to_dict(message))
        return (system, prompt_message_dicts)

    def _convert_claude_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dict
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            else:
                sub_messages = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(TextPromptMessageContent, message_content)
                        sub_message_dict = {"type": "text", "text": message_content.data}
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_content = cast(ImagePromptMessageContent, message_content)
                        if not message_content.data.startswith("data:"):
                            try:
                                image_content = requests.get(message_content.data).content
                                with Image.open(io.BytesIO(image_content)) as img:
                                    mime_type = f"image/{img.format.lower()}"
                                base64_data = base64.b64encode(image_content).decode("utf-8")
                            except Exception as ex:
                                raise ValueError(f"Failed to fetch image data from url {message_content.data}, {ex}")
                        else:
                            data_split = message_content.data.split(";base64,")
                            mime_type = data_split[0].replace("data:", "")
                            base64_data = data_split[1]
                        if mime_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
                            raise ValueError(
                                f"Unsupported image type {mime_type}, only support image/jpeg, image/png, image/gif, and image/webp"
                            )
                        sub_message_dict = {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime_type, "data": base64_data},
                        }
                        sub_messages.append(sub_message_dict)
                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        else:
            raise ValueError(f"Got unknown type {message}")
        return message_dict

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
        :return:md = gml.GenerativeModel(model)
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

    def _convert_tools_to_glm_tool(self, tools: list[PromptMessageTool]) -> "glm.Tool":
        """
        Convert tool messages to glm tools

        :param tools: tool messages
        :return: glm tools
        """
        return glm.Tool(
            function_declarations=[
                glm.FunctionDeclaration(
                    name=tool.name,
                    parameters=glm.Schema(
                        type=glm.Type.OBJECT,
                        properties={
                            key: {
                                "type_": value.get("type", "string").upper(),
                                "description": value.get("description", ""),
                                "enum": value.get("enum", []),
                            }
                            for (key, value) in tool.parameters.get("properties", {}).items()
                        },
                        required=tool.parameters.get("required", []),
                    ),
                )
                for tool in tools
            ]
        )

    def _convert_grounding_to_glm_tool(self, dynamic_threshold: Optional[float]) -> list["glm.Tool"]:
        """
        Convert grounding messages to glm tools

        :param dynamic_threshold: grounding messages
        :return: glm tools
        """
        return [
            glm.Tool.from_google_search_retrieval(
                glm.grounding.GoogleSearchRetrieval(
                    dynamic_retrieval_config=glm.grounding.DynamicRetrievalConfig(
                        mode=glm.grounding.DynamicRetrievalConfig.Mode.MODE_DYNAMIC,
                        dynamic_threshold=dynamic_threshold,
                    )
                )
            )
        ]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            ping_message = SystemPromptMessage(content="ping")
            self._generate(model, credentials, [ping_message], {"max_tokens_to_sample": 5})
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
        config_kwargs = model_parameters.copy()
        config_kwargs["max_output_tokens"] = config_kwargs.pop("max_tokens_to_sample", None)
        
        response_schema = None
        if "json_schema" in config_kwargs:
            response_schema = self._convert_schema_for_vertex(config_kwargs.pop("json_schema"))
        elif "response_schema" in config_kwargs:
            response_schema = self._convert_schema_for_vertex(config_kwargs.pop("response_schema"))
            
        if "response_schema" in config_kwargs:
            config_kwargs.pop("response_schema")
            
        dynamic_threshold = config_kwargs.pop("grounding", None)
        if stop:
            config_kwargs["stop_sequences"] = stop
        service_account_info = (
            json.loads(base64.b64decode(service_account_key))
            if (
                service_account_key := credentials.get("vertex_service_account_key", "")
            )
            else None
        )
        project_id = credentials["vertex_project_id"]
        location = credentials["vertex_location"]
        if service_account_info:
            service_accountSA = service_account.Credentials.from_service_account_info(service_account_info)
            aiplatform.init(credentials=service_accountSA, project=project_id, location=location)
        else:
            aiplatform.init(project=project_id, location=location)
            
        history = []
        system_instruction = ""
        
        for msg in prompt_messages:

            if isinstance(msg, SystemPromptMessage):
                system_instruction = msg.content
            else:
                content = self._format_message_to_glm_content(msg)

                if history and history[-1].role == content.role:
                    
                    all_parts = list(history[-1].parts)
                    all_parts.extend(content.parts)
                    
                    history[-1] = glm.Content(
                        role=history[-1].role,
                        parts=all_parts
                    )

                else:
                    history.append(content)

        google_model = glm.GenerativeModel(model_name=model, system_instruction=system_instruction)

        if dynamic_threshold is not None:
            tools = self._convert_grounding_to_glm_tool(dynamic_threshold=dynamic_threshold)
        else:
            tools = self._convert_tools_to_glm_tool(tools) if tools else None

        mime_type = config_kwargs.pop("response_mime_type", None)
        
        generation_config_params = config_kwargs.copy()
        
        if response_schema:
            generation_config_params["response_schema"] = response_schema
            generation_config_params["response_mime_type"] = "application/json"
        elif mime_type:
            generation_config_params["response_mime_type"] = mime_type
        
        generation_config = glm.GenerationConfig(**generation_config_params)
        
        response = google_model.generate_content(
            contents=history,
            generation_config=generation_config,
            stream=stream,
            tools=tools,
        )
        if stream:
            return self._handle_generate_stream_response(model, credentials, response, prompt_messages)
        return self._handle_generate_response(model, credentials, response, prompt_messages)

    def _handle_generate_response(
        self, model: str, credentials: dict, response: glm.GenerationResponse, prompt_messages: list[PromptMessage]
    ) -> LLMResult:
        """
        Handle llm response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response
        """
        assistant_prompt_message = AssistantPromptMessage(content=response.candidates[0].content.parts[0].text)
        prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
        completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        result = LLMResult(model=model, prompt_messages=prompt_messages, message=assistant_prompt_message, usage=usage)
        return result

    def _handle_generate_stream_response(
        self, model: str, credentials: dict, response: glm.GenerationResponse, prompt_messages: list[PromptMessage]
    ) -> Generator:
        """
        Handle llm stream response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator result
        """
        index = -1
        for chunk in response:
            candidate = chunk.candidates[0]
            for part in candidate.content.parts:
                assistant_prompt_message = AssistantPromptMessage(content="")
                if part.text:
                    assistant_prompt_message.content += part.text
                if part.function_call:
                    assistant_prompt_message.tool_calls = [
                        AssistantPromptMessage.ToolCall(
                            id=part.function_call.name,
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name=part.function_call.name,
                                arguments=json.dumps(dict(part.function_call.args.items())),
                            ),
                        )
                    ]
                index += 1
                if not hasattr(candidate, "finish_reason") or not candidate.finish_reason:
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(index=index, message=assistant_prompt_message),
                    )
                else:
                    prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
                    completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])
                    usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

                    reference_lines = []
                    grounding_chunks = None
                    try:
                        grounding_chunks = chunk.candidates[0].grounding_metadata.grounding_chunks
                    except AttributeError:
                        try:
                            candidate_dict = chunk.candidates[0].to_dict()
                            grounding_chunks = candidate_dict.get("grounding_metadata", {}).get("grounding_chunks", [])
                        except Exception:
                            grounding_chunks = []

                    if grounding_chunks:
                        for gc in grounding_chunks:
                            try:
                                title = gc.web.title
                                uri = gc.web.uri
                            except AttributeError:
                                web_info = gc.get("web", {})
                                title = web_info.get("title")
                                uri = web_info.get("uri")
                            if title and uri:
                                reference_lines.append(f"<li><a href='{uri}'>{title}</a></li>")

                    if reference_lines:
                        reference_lines.insert(0, "<ol>")
                        reference_lines.append("</ol>")
                        reference_section = "\n\nGrounding Sources\n" + "\n".join(reference_lines)
                    else:
                        reference_section = ""

                    integrated_text = f"{assistant_prompt_message.content}{reference_section}"
                    assistant_message_with_refs = AssistantPromptMessage(content=integrated_text)

                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=assistant_message_with_refs,
                            finish_reason=str(candidate.finish_reason),
                            usage=usage,
                        ),
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

    def _format_message_to_glm_content(self, message: PromptMessage) -> glm.Content:
        """
        Format a single message into glm.Content for Google API

        :param message: one PromptMessage
        :return: glm Content representation of message
        """
        if isinstance(message, UserPromptMessage):
            parts = []
            if isinstance(message.content, str):
                parts.append(glm.Part.from_text(message.content))
            elif isinstance(message.content, list):
                for c in message.content:
                    if c.type == PromptMessageContentType.TEXT:
                        parts.append(glm.Part.from_text(c.data))
                    elif c.type in [
                        PromptMessageContentType.IMAGE,
                        PromptMessageContentType.DOCUMENT,
                        PromptMessageContentType.AUDIO,
                        PromptMessageContentType.VIDEO
                    ]:
                        data = c.base64_data
                        mime_type = getattr(c, 'mime_type', None)
                        parts.append(glm.Part.from_data(data=data, mime_type=mime_type))
                    else:
                        raise ValueError(f"Unsupported content type: {c.type}")
            glm_content = glm.Content(role="user", parts=parts)
            return glm_content
        elif isinstance(message, AssistantPromptMessage):
            if message.content:
                glm_content = glm.Content(role="model", parts=[glm.Part.from_text(message.content)])
            if message.tool_calls:
                glm_content = glm.Content(
                    role="model",
                    parts=[
                        glm.Part.from_function_response(
                            glm.FunctionCall(
                                name=message.tool_calls[0].function.name,
                                args=json.loads(message.tool_calls[0].function.arguments),
                            )
                        )
                    ],
                )
            return glm_content
        elif isinstance(message, ToolPromptMessage):
            glm_content = glm.Content(
                role="function",
                parts=[
                    glm.Part(
                        function_response=glm.FunctionResponse(
                            name=message.name, response={"response": message.content}
                        )
                    )
                ],
            )
            return glm_content
        else:
            raise ValueError(f"Got unknown type {message}")

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the ermd = gml.GenerativeModel(model) error type thrown to the caller
        The value is the md = gml.GenerativeModel(model) error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke emd = gml.GenerativeModel(model) error mapping
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

    def _convert_schema_for_vertex(self, schema):
        """
        Convert JSON schema to Vertex AI's expected format
        
        :param schema: The original JSON schema
        :return: Converted schema for Vertex AI
        """
        import json
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                pass
        
        if isinstance(schema, dict):
            converted_schema = {}
            
            for key, value in schema.items():
                if key == "type" and isinstance(value, str):
                    converted_schema[key] = value.upper()
                    
                elif key == "properties" and isinstance(value, dict):
                    converted_props = {}
                    for prop_name, prop_def in value.items():
                        converted_props[prop_name] = self._convert_schema_for_vertex(prop_def)
                    converted_schema[key] = converted_props
                    
                elif key == "items" and isinstance(value, dict):
                    converted_schema[key] = self._convert_schema_for_vertex(value)
                    
                elif key == "enum" and isinstance(value, list):
                    converted_schema[key] = value
                    
                else:
                    if isinstance(value, (dict, list)):
                        converted_schema[key] = self._convert_schema_for_vertex(value)
                    else:
                        converted_schema[key] = value
                        
            return converted_schema
            
        elif isinstance(schema, list):
            return [self._convert_schema_for_vertex(item) for item in schema]
            
        else:
            return schema