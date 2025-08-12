import base64
import json
import logging
import os
import re
import tempfile
import time
from collections.abc import Generator, Iterator, Sequence
from typing import Optional, Union, Mapping, Any, Tuple, List, TypeVar

import requests
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    MultiModalPromptMessageContent,
    PromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
    PromptMessageContentUnionTypes,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from google import genai
from google.genai import errors, types

from .utils import FileCache

file_cache = FileCache()

_MMC = TypeVar("_MMC", bound=MultiModalPromptMessageContent)


class GoogleLargeLanguageModel(LargeLanguageModel):
    is_thinking = None

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
    ) -> Union[LLMResult, Generator[LLMResultChunk]]:
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
        _ = user
        return self._generate(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

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

        # TODO(QIN2DIM): Fix the issue of inaccurate counting of Gemini Tokens
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

    @staticmethod
    def _convert_tools_to_gemini_tool(tools: list[PromptMessageTool]) -> types.Tool:
        """
        Convert tool messages to google-genai's Tool Type.

        :param tools: tool messages
        :return: Gemini tools
        """
        function_declarations = []
        for tool in tools:
            properties = {}
            for key, value in tool.parameters.get("properties", {}).items():
                property_def = {"type": "STRING", "description": value.get("description", "")}
                if "enum" in value:
                    property_def["enum"] = value["enum"]
                properties[key] = property_def

            if properties:
                parameters = types.Schema(
                    type=types.Type.OBJECT,
                    properties=properties,
                    required=tool.parameters.get("required", []),
                )
            else:
                parameters = None

            functions = types.FunctionDeclaration(
                name=tool.name, parameters=parameters, description=tool.description
            )
            function_declarations.append(functions)

        return types.Tool(function_declarations=function_declarations)

    @staticmethod
    def _convert_one_message_to_text(message: PromptMessage) -> str:
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

    @staticmethod
    def _upload_file_content_to_google(
        message_content: _MMC, genai_client: genai.Client, file_server_url_prefix: str | None = None
    ) -> Tuple[str, str]:

        key = f"{message_content.type.value}:{hash(message_content.data)}"
        if file_cache.exists(key):
            value = file_cache.get(key).split(";")
            return value[0], value[1]

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            if message_content.base64_data:
                file_content = base64.b64decode(message_content.base64_data)
                temp_file.write(file_content)
            else:
                try:
                    file_url = message_content.url
                    if file_server_url_prefix:
                        file_url = f"{file_server_url_prefix.rstrip('/')}/files{message_content.url.split('/files')[-1]}"
                    if not file_url.startswith("https://") and not file_url.startswith("http://"):
                        raise ValueError("Set FILES_URL env first!")
                    response: requests.Response = requests.get(file_url)
                    response.raise_for_status()
                    temp_file.write(response.content)
                except Exception as ex:
                    raise ValueError(f"Failed to fetch data from url {file_url} {ex}")
            temp_file.flush()

        file = genai_client.files.upload(
            file=temp_file.name, config=types.UploadFileConfig(mime_type=message_content.mime_type)
        )

        while file.state.name == "PROCESSING":
            time.sleep(5)
            file = genai_client.files.get(name=file.name)

        # google will delete your upload files in 2 days.
        file_cache.setex(key, 47 * 60 * 60, f"{file.uri};{file.mime_type}")

        try:
            os.unlink(temp_file.name)
        except PermissionError:
            # windows may raise permission error
            pass

        return file.uri, file.mime_type

    @staticmethod
    def _render_grounding_source(grounding_metadata: types.GroundingMetadata) -> str:
        """
        Render google search source links
        """
        result = "\n\n**Search Sources:**\n"
        for index, entry in enumerate(grounding_metadata.grounding_chunks, start=1):
            result += f"{index}. [{entry.web.title}]({entry.web.uri})\n"
        return result

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        """
        return {
            InvokeConnectionError: [errors.APIError, errors.ClientError],
            InvokeServerUnavailableError: [errors.ServerError],
            InvokeBadRequestError: [
                errors.ClientError,
                errors.UnknownFunctionCallArgumentError,
                errors.UnsupportedFunctionError,
                errors.FunctionInvocationError,
            ],
        }

    @staticmethod
    def _calculate_tokens_from_usage_metadata(
        usage_metadata: types.GenerateContentResponseUsageMetadata | None,
    ) -> tuple[int, int]:
        """
        Calculate prompt and completion tokens from usage metadata.

        :param usage_metadata: Usage metadata from Gemini response
        :return: Tuple of (prompt_tokens, completion_tokens)
        """
        if not usage_metadata:
            return 0, 0

        # The pricing of tokens varies depending on the input modality.
        prompt_tokens_standard = 0

        # [ Pricing ]
        # https://ai.google.dev/gemini-api/docs/pricing?hl=zh-cn#gemini-2.5-pro
        # FIXME: Currently, Dify's pricing model cannot cover the tokens of multimodal resources
        # FIXME: Unable to track caching, Grounding, Live API
        for _mtc in usage_metadata.prompt_tokens_details:
            if _mtc.modality in [
                types.MediaModality.TEXT,
                types.MediaModality.IMAGE,
                types.MediaModality.VIDEO,
                types.MediaModality.MODALITY_UNSPECIFIED,
                types.MediaModality.AUDIO,
                types.MediaModality.DOCUMENT,
            ]:
                prompt_tokens_standard += _mtc.token_count

        # Number of tokens present in thoughts output.
        thoughts_token_count = usage_metadata.thoughts_token_count or 0
        # Number of tokens in the response(s).
        candidates_token_count = usage_metadata.candidates_token_count or 0
        # The reasoning content and final answer of the Gemini model are priced using the same standard.
        completion_tokens = thoughts_token_count + candidates_token_count
        # The `prompt_tokens` includes the historical conversation QA plus the current input.
        prompt_tokens = prompt_tokens_standard

        return prompt_tokens, completion_tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            ping_message = UserPromptMessage(content="ping")
            self._generate(
                model=model,
                credentials=credentials,
                prompt_messages=[ping_message],
                stream=False,
                model_parameters={"max_output_tokens": 5},
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _generate(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: Mapping[str, Any],
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator[LLMResultChunk]]:
        conditions: list[bool] = [
            bool(model_parameters.get("json_schema")),
            bool(model_parameters.get("grounding")),
            bool(tools),
        ]
        if sum(conditions) >= 2:
            raise InvokeError(
                "gemini not support use multiple features at same time: json_schema, grounding, tools+knowledge"
            )

        # == InitConfig == #

        config = types.GenerateContentConfig()
        genai_client = genai.Client(api_key=credentials["google_api_key"])

        # == ChatConfig == #

        if schema := model_parameters.get("json_schema"):
            try:
                schema = json.loads(schema)
            except (TypeError, ValueError) as exc:
                raise InvokeError("Invalid JSON Schema") from exc
            config.response_schema = schema
            config.response_mime_type = "application/json"

        if stop:
            config.stop_sequences = stop

        config.top_p = model_parameters.get("top_p", None)
        config.top_k = model_parameters.get("top_k", None)
        config.temperature = model_parameters.get("temperature", None)
        config.max_output_tokens = model_parameters.get("max_output_tokens", None)

        # Build contents from prompt messages
        file_server_url_prefix = credentials.get("file_url") or None
        contents = self._build_gemini_contents(
            prompt_messages=prompt_messages,
            genai_client=genai_client,
            config=config,
            file_server_url_prefix=file_server_url_prefix,
        )

        # == ThinkingConfig == #

        # To reduce ambiguity, when both configurable parameters are not specified,
        # this configuration should not be explicitly declared.

        # For models that do not support the reasoning mode (such as gemini-2.0-flash),
        # incorrectly setting include_thoughts to True will not cause a system error.

        # When include_thoughts is True, thinking_budget must not be None to obtain valid thinking content.

        # However, setting thinking_budget for models that do not support the thinking mode
        # will result in a 400 INVALID_ARGUMENT error.

        include_thoughts = model_parameters.get("include_thoughts", None)
        thinking_budget = model_parameters.get("thinking_budget", None)
        thinking_mode = model_parameters.get("thinking_mode", None)

        # Must be explicitly handled here, where the three states True, False, and None each have specific meanings.
        if thinking_mode is None:
            if isinstance(thinking_budget, int) and thinking_budget == 0:
                thinking_budget = -1
        elif thinking_mode is False:
            thinking_budget = 0
        elif thinking_mode:
            if (isinstance(thinking_budget, int) and thinking_budget == 0) or (
                thinking_budget is None
            ):
                thinking_budget = -1

        config.thinking_config = types.ThinkingConfig(
            include_thoughts=include_thoughts, thinking_budget=thinking_budget
        )

        # == ToolUseConfig == #

        config.tools = []
        if model_parameters.get("grounding"):
            config.tools.append(types.Tool(google_search=types.GoogleSearch()))
        if tools:
            config.tools.append(self._convert_tools_to_gemini_tool(tools))

        # == InvokeModel == #

        if stream:
            response = genai_client.models.generate_content_stream(
                model=model, contents=contents, config=config
            )
            return self._handle_generate_stream_response(
                model, credentials, response, prompt_messages
            )

        response = genai_client.models.generate_content(
            model=model, contents=contents, config=config
        )
        return self._handle_generate_response(model, credentials, response, prompt_messages)

    def _build_gemini_contents(
        self,
        prompt_messages: list[PromptMessage],
        genai_client: genai.Client,
        config: types.GenerateContentConfig,
        file_server_url_prefix: str | None = None,
    ) -> List[types.Content]:
        """
        Build Gemini contents from prompt messages with proper role alternation

        :param prompt_messages: list of prompt messages
        :param genai_client: Google GenAI client
        :param config: GenerateContentConfig object
        :param file_server_url_prefix: optional file server URL prefix
        :return: list of Gemini Content objects ready for use
        """
        contents = []

        for msg in prompt_messages:
            content = self._format_message_to_gemini_content(
                msg, genai_client, config, file_server_url_prefix
            )

            if not content:
                continue

            # Merge consecutive messages with same role for proper alternation
            if contents and contents[-1].role == content.role:
                contents[-1].parts.extend(content.parts)
            else:
                contents.append(content)

        return contents

    def _format_message_to_gemini_content(
        self,
        message: PromptMessage,
        genai_client: genai.Client,
        config: types.GenerateContentConfig,
        file_server_url_prefix: str | None = None,
    ) -> types.Content | None:
        """
        Format a single message into Contents for Google GenAI SDK

        :param message: one PromptMessage
        :return: Gemini Content representation of message
        """

        # Helper function to build parts from content
        def build_parts(content: str | List[PromptMessageContentUnionTypes]) -> List[types.Part]:
            if isinstance(content, str):
                return [types.Part.from_text(text=content)]

            parts_ = []
            for obj in content:
                if obj.type == PromptMessageContentType.TEXT:
                    parts_.append(types.Part.from_text(text=obj.data))
                else:
                    uri, mime_type = self._upload_file_content_to_google(
                        obj, genai_client, file_server_url_prefix
                    )
                    parts_.append(types.Part.from_uri(file_uri=uri, mime_type=mime_type))
            return parts_

        # Process different message types
        if isinstance(message, UserPromptMessage):
            return types.Content(role="user", parts=build_parts(message.content))

        elif isinstance(message, AssistantPromptMessage):
            parts = []

            # Handle text content (remove thinking tags)
            if message.content:
                content_text = re.sub(
                    r"^<think>.*?</think>\s*", "", message.content, count=1, flags=re.DOTALL
                )
                if content_text:
                    parts.append(types.Part.from_text(text=content_text))

            # Handle tool calls
            # https://ai.google.dev/gemini-api/docs/function-calling?hl=zh-cn&example=chart#how-it-works
            if message.tool_calls:
                call = message.tool_calls[0]
                parts.append(
                    types.Part.from_function_call(
                        name=call.function.name, args=json.loads(call.function.arguments)
                    )
                )

            return types.Content(role="model", parts=parts)

        elif isinstance(message, SystemPromptMessage):
            # String content -> system instruction
            if isinstance(message.content, str):
                config.system_instruction = message.content
                return None

            # List content -> convert to user message (Files[] compatibility)
            if isinstance(message.content, list):
                return types.Content(role="user", parts=build_parts(message.content))

        elif isinstance(message, ToolPromptMessage):
            return types.Content(
                # The role `function` does not exist.
                # https://googleapis.github.io/python-genai/genai.html#genai.types.Content.role
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=message.name, response={"response": message.content}
                    )
                ],
            )

        else:
            raise ValueError(f"Unknown message type: {type(message).__name__}")

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: types.GenerateContentResponse,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        """
        Handle llm response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response
        """
        # transform assistant message to prompt message
        assistant_prompt_message = AssistantPromptMessage(content=response.text)

        # calculate num tokens
        prompt_tokens, completion_tokens = self._calculate_tokens_from_usage_metadata(
            response.usage_metadata
        )

        # Fallback to manual calculation if tokens are not available
        if prompt_tokens == 0 or completion_tokens == 0:
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
            completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])

        # transform usage
        # copy credentials to avoid modifying the original dict
        usage = self._calc_response_usage(
            model=model,
            credentials=dict(credentials),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        # transform response
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
        )

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Iterator[types.GenerateContentResponse],
        prompt_messages: list[PromptMessage],
    ) -> Generator[LLMResultChunk]:
        """
        Handle llm stream response

        # -- Usage Sample -- #
        chunk.usage_metadata=GenerateContentResponseUsageMetadata(
          candidates_token_count=58,
          prompt_token_count=24,
          prompt_tokens_details=[
            ModalityTokenCount(
              modality=<MediaModality.TEXT: 'TEXT'>,
              token_count=24
            ),
          ],
          thoughts_token_count=862,
          total_token_count=944
        )

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator result
        """
        index = -1
        prompt_tokens = 0
        completion_tokens = 0
        self.is_thinking = False

        for chunk in response:
            if not chunk.candidates:
                continue
            for candidate in chunk.candidates:
                if not candidate.content or not candidate.content.parts:
                    continue

                message = self._parse_parts(candidate.content.parts)
                index += len(candidate.content.parts)

                # if the stream is not finished, yield the chunk
                if not candidate.finish_reason:
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=list(prompt_messages),
                        delta=LLMResultChunkDelta(index=index, message=message),
                    )
                # if the stream is finished, yield the chunk and the finish reason
                else:
                    # If we're still in thinking mode at the end, close it
                    if self.is_thinking:
                        message.content.append(TextPromptMessageContent(data="\n\n</think>"))

                    prompt_tokens, completion_tokens = self._calculate_tokens_from_usage_metadata(
                        chunk.usage_metadata
                    )

                    # Fallback to manual calculation if tokens are not available
                    if prompt_tokens == 0 or completion_tokens == 0:
                        prompt_tokens = self.get_num_tokens(
                            model=model, credentials=credentials, prompt_messages=prompt_messages
                        )
                        completion_tokens = self.get_num_tokens(
                            model=model, credentials=credentials, prompt_messages=[message]
                        )
                    usage = self._calc_response_usage(
                        model=model,
                        credentials=dict(credentials),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=list(prompt_messages),
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=message,
                            finish_reason=candidate.finish_reason,
                            usage=usage,
                        ),
                    )

    def _parse_parts(self, parts: Sequence[types.Part], /) -> AssistantPromptMessage:
        """

        Args:
            parts: [
            {
              "video_metadata": null,
              "thought": null,
              "inline_data": null,
              "file_data": null,
              "thought_signature": null,
              "code_execution_result": null,
              "executable_code": null,
              "function_call": null,
              "function_response": null,
              "text": "<|CHUNK|>"
            }
          ]

        Returns:

        """
        contents: list[PromptMessageContent] = []
        function_calls = []
        for part in parts:
            if part.text:
                # Check if we need to start thinking mode
                if part.thought is True and not self.is_thinking:
                    contents.append(TextPromptMessageContent(data="<think>\n\n"))
                    self.is_thinking = True

                # Check if we need to end thinking mode
                elif part.thought is None and self.is_thinking:
                    contents.append(TextPromptMessageContent(data="\n\n</think>"))
                    self.is_thinking = False

                contents.append(TextPromptMessageContent(data=part.text))

            # A predicted [FunctionCall] returned from the model that contains a string
            # representing the [FunctionDeclaration.name] with the parameters and their values.
            if part.function_call:
                function_call_part: types.FunctionCall = part.function_call
                # Generate a unique ID since Gemini API doesn't provide one
                function_call_id = f"gemini_call_{function_call_part.name}_{time.time_ns()}"
                logging.info(f"Generated function call ID: {function_call_id}")
                function_call_name = function_call_part.name
                function_call_args = function_call_part.args
                if not isinstance(function_call_name, str):
                    raise InvokeError("function_call_name received is not a string")
                if not isinstance(function_call_args, dict):
                    raise InvokeError("function_call_args received is not a dict")
                tool_call = AssistantPromptMessage.ToolCall(
                    id=function_call_id,
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=function_call_name, arguments=json.dumps(function_call_args)
                    ),
                )
                function_calls.append(tool_call)

            # Inlined bytes data
            if part.inline_data:
                inline_data = part.inline_data
                mime_type = inline_data.mime_type
                data = inline_data.data
                if mime_type is None:
                    raise InvokeError("receive inline_data with no mime_type")
                if data is None:
                    raise InvokeError("receive inline_data with no data")
                if mime_type.startswith("image/"):
                    mime_subtype = mime_type.split("/", maxsplit=1)[-1]
                    # Here the data returned by genai-sdk is already a base64-encoded
                    # byte string, so just decode it to utf-8 string is enough.
                    contents.append(
                        ImagePromptMessageContent(
                            format=mime_subtype,
                            base64_data=base64.b64encode(data).decode(),
                            mime_type=mime_type,
                        )
                    )
                else:
                    raise InvokeError(f"unsupported mime_type {mime_type}")

        # FIXME: This is a workaround to fix the typing issue in the dify_plugin
        # https://github.com/langgenius/dify-plugin-sdks/issues/41
        # fixed_contents = [content.model_dump(mode="json") for content in contents]
        message = AssistantPromptMessage(
            content=contents, tool_calls=function_calls  # type: ignore
        )
        return message
