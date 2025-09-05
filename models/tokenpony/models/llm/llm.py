import requests
import codecs
from pydantic import TypeAdapter, ValidationError
from typing import Any, Dict, Generator, List, Optional
from typing import Optional, Union, Any
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMMode
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    UserPromptMessage,
    TextPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageContentType,
    AssistantPromptMessage,
    PromptMessageContent
)
from dify_plugin.errors.model import InvokeError
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.interfaces.model.openai_compatible.llm import _increase_tool_call

# 导入 logging 和自定义处理器
import logging
from dify_plugin.config.logger_format import plugin_logger_handler

# 使用自定义处理器设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class TokenponyLargeLanguageModel(OAICompatLargeLanguageModel):
    """
    A text-only large language model adapter for Dify with reasoning support.
    """

    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = "https://dify.vip-api.tokenpony.cn/v1"
        credentials["mode"] = self.get_model_mode(model).value
        schema = self.get_model_schema(model, credentials)
        # if schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL}.intersection(
        #     schema.features or []
        # ):
        #     credentials["function_calling_type"] = "tool_call"

        # Add TokenPony specific headers for rankings on TokenPony.ai
        logger.info(f"TokenponyLargeLanguageModel._update_credential: credentials={credentials}")
        #获取API Key
        openai_api_key = credentials["openai_api_key"]
        credentials["extra_headers"] = {
            "Authorization": "Bearer "+openai_api_key,
            "X-Title": "Dify"
        }

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
        self._update_credential(model, credentials)
        logger.info(f"TokenponyLargeLanguageModel._invoke: model={model}, credentials={credentials}, prompt_messages={prompt_messages}, model_parameters={model_parameters}, tools={tools}, stop={stop}, stream={stream}, user={user}")
        
        # Only convert file content to text descriptions for models that don't support vision
        model_schema = self.get_model_schema(model, credentials)
        # if not (model_schema and ModelFeature.VISION in (model_schema.features or [])):
        #     prompt_messages = self._convert_files_to_text(prompt_messages)

        # if model in IMAGE_GENERATION_MODELS:
        #     model_parameters["modalities"] = ["image", "text"]
        # else:
        # reasoning
        reasoning_params = {}
        reasoning_budget = model_parameters.pop('reasoning_budget', None)
        enable_thinking = model_parameters.pop('enable_thinking', None)
        if enable_thinking == 'dynamic':
            reasoning_budget = -1
        if reasoning_budget is not None:
            reasoning_params['max_tokens'] = reasoning_budget
        reasoning_effort = model_parameters.pop('reasoning_effort', None)
        if reasoning_effort is not None:
            reasoning_params['effort'] = reasoning_effort
        exclude_reasoning_tokens = model_parameters.pop('exclude_reasoning_tokens', None)
        if exclude_reasoning_tokens is not None:
            reasoning_params['exclude'] = exclude_reasoning_tokens
        if reasoning_params:
            model_parameters['reasoning'] = reasoning_params
        return self._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        response_json: dict = response.json()

        completion_type = LLMMode.value_of(credentials["mode"])

        output = response_json["choices"][0]
        message_id = response_json.get("id")

        response_content = ""
        tool_calls = None
        function_calling_type = credentials.get("function_calling_type", "no_call")
        if completion_type is LLMMode.CHAT:
            response_content = output.get("message", {})["content"]
            if function_calling_type == "tool_call":
                tool_calls = output.get("message", {}).get("tool_calls")
            elif function_calling_type == "function_call":
                tool_calls = output.get("message", {}).get("function_call")

        elif completion_type is LLMMode.COMPLETION:
            response_content = output["text"]

        contents: list[PromptMessageContent] = [TextPromptMessageContent(data=response_content)]
        contents.extend(
            self._parse_image_part(output, stream=False)
        )

        assistant_message = AssistantPromptMessage(
            content=contents, tool_calls=[]
        )

        if tool_calls:
            if function_calling_type == "tool_call":
                assistant_message.tool_calls = self._extract_response_tool_calls(tool_calls)
            elif function_calling_type == "function_call":
                assistant_message.tool_calls = [self._extract_response_function_call(tool_calls)]

        usage = response_json.get("usage")
        if usage:
            # transform usage
            prompt_tokens = usage["prompt_tokens"]
            completion_tokens = usage["completion_tokens"]
        else:
            # calculate num tokens
            assert prompt_messages[0].content is not None
            prompt_tokens = self._num_tokens_from_string(model, prompt_messages[0].content)
            assert assistant_message.content is not None
            completion_tokens = self._num_tokens_from_string(model, assistant_message.content)

        # transform usage
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        # transform response
        result = LLMResult(
            id=message_id,
            model=response_json["model"],
            message=assistant_message,
            usage=usage,
        )

        return result

    def _handle_generate_stream_response(
        self, model: str, credentials: dict, response: requests.Response, prompt_messages: list[PromptMessage]
    ) -> Generator:
        """
        Handle llm stream response

        :param model: model name
        :param credentials: model credentials
        :param response: streamed response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator
        """
        chunk_index = 0
        full_assistant_content = ""
        tools_calls: list[AssistantPromptMessage.ToolCall] = []
        finish_reason = None
        usage = None
        is_reasoning_started = False
        # delimiter for stream response, need unicode_escape
        delimiter = credentials.get("stream_mode_delimiter", "\n\n")
        delimiter = codecs.decode(delimiter, "unicode_escape")
        for chunk in response.iter_lines(decode_unicode=True, delimiter=delimiter):
            chunk = chunk.strip()
            if chunk:
                # ignore sse comments
                if chunk.startswith(":"):
                    continue
                decoded_chunk = chunk.strip().removeprefix("data:").lstrip()
                if decoded_chunk == "[DONE]":  # Some provider returns "data: [DONE]"
                    continue

                try:
                    chunk_json: dict = TypeAdapter(dict[str, Any]).validate_json(decoded_chunk)
                # stream ended
                except ValidationError:
                    yield self._create_final_llm_result_chunk(
                        index=chunk_index + 1,
                        message=AssistantPromptMessage(content=""),
                        finish_reason="Non-JSON encountered.",
                        usage=usage,
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        full_content=full_assistant_content,
                    )
                    break
                # handle the error here. for issue #11629
                if chunk_json.get("error") and chunk_json.get("choices") is None:
                    raise ValueError(chunk_json.get("error"))

                if chunk_json:  # noqa: SIM102
                    if u := chunk_json.get("usage"):
                        usage = u
                if not chunk_json or len(chunk_json["choices"]) == 0:
                    continue

                choice = chunk_json["choices"][0]
                finish_reason = chunk_json["choices"][0].get("finish_reason")
                chunk_index += 1

                if "delta" in choice:
                    delta = choice["delta"]
                    delta_content, is_reasoning_started = self._wrap_thinking_by_reasoning_content(
                        delta, is_reasoning_started
                    )
                    # if model in IMAGE_GENERATION_MODELS:
                    #     if delta_content:
                    #         delta_content = [TextPromptMessageContent(data=delta_content)]
                    #     else:
                    #         delta_content = []
                    #     delta_content.extend(
                    #         self._parse_image_part(delta, stream=True)  # type: ignore
                    #     )

                    assistant_message_tool_calls = None

                    if "tool_calls" in delta and credentials.get("function_calling_type", "no_call") == "tool_call":
                        assistant_message_tool_calls = delta.get("tool_calls", None)
                    elif (
                        "function_call" in delta
                        and credentials.get("function_calling_type", "no_call") == "function_call"
                    ):
                        assistant_message_tool_calls = [
                            {"id": "tool_call_id", "type": "function", "function": delta.get("function_call", {})}
                        ]

                    # extract tool calls from response
                    if assistant_message_tool_calls:
                        tool_calls = self._extract_response_tool_calls(assistant_message_tool_calls)
                        _increase_tool_call(tool_calls, tools_calls)

                    if not delta_content:
                        continue

                    # transform assistant message to prompt message
                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_content,
                    )

                    if isinstance(delta_content, str):
                        full_assistant_content += delta_content
                    else:
                        full_assistant_content += "".join([content.data for content in delta_content])
                elif "text" in choice:
                    choice_text = choice.get("text", "")
                    if choice_text == "":
                        continue

                    # transform assistant message to prompt message
                    assistant_prompt_message = AssistantPromptMessage(content=choice_text)
                    full_assistant_content += choice_text
                else:
                    continue

                yield LLMResultChunk(
                    model=model,
                    delta=LLMResultChunkDelta(
                        index=chunk_index,
                        message=assistant_prompt_message,
                    ),
                )

            chunk_index += 1

        if tools_calls:
            yield LLMResultChunk(
                model=model,
                delta=LLMResultChunkDelta(
                    index=chunk_index,
                    message=AssistantPromptMessage(tool_calls=tools_calls, content=""),
                ),
            )

        yield self._create_final_llm_result_chunk(
            index=chunk_index,
            message=AssistantPromptMessage(content=""),
            finish_reason=finish_reason,
            usage=usage,
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            full_content=full_assistant_content,
        )
    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(model, credentials)
        return super().validate_credentials(model, credentials)

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
        self._update_credential(model, credentials)
        return super()._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def _wrap_thinking_by_reasoning_content(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        If the reasoning response is from delta.get("reasoning") or delta.get("reasoning_content"),
        we wrap it with HTML think tag.

        :param delta: delta dictionary from LLM streaming response
        :param is_reasoning: is reasoning
        :return: tuple of (processed_content, is_reasoning)
        """

        content = delta.get("content") or ""
        # NOTE(hzw): OpenRouter uses "reasoning" instead of "reasoning_content".
        reasoning_content = delta.get("reasoning") or delta.get("reasoning_content")

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
    def _generate_block_as_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        user: Optional[str] = None,
    ) -> Generator:
        resp = super()._generate(model, credentials, prompt_messages, model_parameters, tools, stop, False, user)
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=resp.message,
                usage=self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens,
                ),
                finish_reason="stop",
            ),
        )
    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        return super().get_customizable_model_schema(model, credentials)
    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        self._update_credential(model, credentials)
        return super().get_num_tokens(model, credentials, prompt_messages, tools)
