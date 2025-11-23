import json
import logging
import re
from collections.abc import Generator
from decimal import Decimal
from typing import Any, Optional, Union, cast
from urllib.parse import urljoin

import requests
from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
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
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)

# Module-level constants for readability and maintainability
_MAX_TOOL_CALLS = 1000
_MICRO_CHUNK_SIZE = 16
_TRUTHY_VALUES = {"true", "supported", "yes", "1"}


class OllamaLargeLanguageModel(LargeLanguageModel):
    """
    Model class for Ollama large language model.
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
        return self._generate(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
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
        :return:
        """
        model_mode = self.get_model_mode(model, credentials)
        if model_mode == LLMMode.CHAT:
            return self._num_tokens_from_messages(prompt_messages)
        else:
            first_prompt_message = prompt_messages[0]
            if isinstance(first_prompt_message.content, str):
                text = first_prompt_message.content
            elif isinstance(first_prompt_message.content, list):
                text = ""
                for message_content in first_prompt_message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(
                            TextPromptMessageContent, message_content
                        )
                        text = message_content.data
                        break
            return self._get_num_tokens_by_gpt2(text)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._generate(
                model=model,
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="ping")],
                model_parameters={"num_predict": 5},
                stream=False,
            )
        except InvokeError as ex:
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: {ex.description}"
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: {str(ex)}"
            )

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
        Invoke llm completion model

        :param model: model name
        :param credentials: credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        headers = {"Content-Type": "application/json"}
        endpoint_url = credentials["base_url"]
        if not endpoint_url.endswith("/"):
            endpoint_url += "/"
        data = {"model": model, "stream": stream}
        if "format" in model_parameters:
            data["format"] = model_parameters["format"]
            del model_parameters["format"]
        if "keep_alive" in model_parameters:
            data["keep_alive"] = model_parameters["keep_alive"]
            del model_parameters["keep_alive"]
        if "json_schema" in model_parameters:
            try:
                data["format"] = json.loads(model_parameters["json_schema"])
            except json.JSONDecodeError:
                data["format"] = "json"
            del model_parameters["json_schema"]
        data["options"] = model_parameters or {}
        # Add think support
        if "think" in model_parameters and model_parameters["think"] is not None:
            data["think"] = bool(model_parameters["think"])
            del model_parameters["think"]
        if stop:
            data["options"]["stop"] = stop
        completion_type = LLMMode.value_of(credentials["mode"])
        if completion_type is LLMMode.CHAT:
            endpoint_url = urljoin(endpoint_url, "api/chat")
            data["messages"] = [
                self._convert_prompt_message_to_dict(m) for m in prompt_messages
            ]
            if tools:
                data["tools"] = [
                    self._convert_prompt_message_tool_to_dict(tool) for tool in tools
                ]
        else:
            endpoint_url = urljoin(endpoint_url, "api/generate")
            first_prompt_message = prompt_messages[0]
            if isinstance(first_prompt_message, UserPromptMessage):
                first_prompt_message = cast(UserPromptMessage, first_prompt_message)
                if isinstance(first_prompt_message.content, str):
                    data["prompt"] = first_prompt_message.content
                elif isinstance(first_prompt_message.content, list):
                    text = ""
                    images = []
                    for message_content in first_prompt_message.content:
                        if message_content.type == PromptMessageContentType.TEXT:
                            message_content = cast(
                                TextPromptMessageContent, message_content
                            )
                            text = message_content.data
                        elif message_content.type == PromptMessageContentType.IMAGE:
                            message_content = cast(
                                ImagePromptMessageContent, message_content
                            )
                            image_data = re.sub(
                                "^data:image\\/[a-zA-Z]+;base64,",
                                "",
                                message_content.data,
                            )
                            images.append(image_data)
                    data["prompt"] = text
                    data["images"] = images
        response = requests.post(
            endpoint_url, headers=headers, json=data, timeout=(10, 300), stream=stream
        )
        response.encoding = "utf-8"
        if response.status_code != 200:
            raise InvokeError(
                f"API request failed with status code {response.status_code}: {response.text}"
            )
        if stream:
            return self._handle_generate_stream_response(
                model, credentials, completion_type, response, prompt_messages
            )
        return self._handle_generate_response(
            model, credentials, completion_type, response, prompt_messages, tools
        )

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        completion_type: LLMMode,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]],
    ) -> LLMResult:
        """
        Handle llm completion response

        :param model: model name
        :param credentials: model credentials
        :param completion_type: completion type
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm result
        """
        response_json = response.json()
        tool_calls = []
        if completion_type is LLMMode.CHAT:
            message = response_json.get("message", {})
            response_content = message.get("content", "")
            response_tool_calls = message.get("tool_calls", [])
            tool_calls = [
                self._extract_response_tool_call(tool_call)
                for tool_call in response_tool_calls
            ]
        else:
            response_content = response_json["response"]
        assistant_message = AssistantPromptMessage(
            content=response_content, tool_calls=tool_calls
        )
        if "prompt_eval_count" in response_json and "eval_count" in response_json:
            prompt_tokens = response_json["prompt_eval_count"]
            completion_tokens = response_json["eval_count"]
        else:
            prompt_tokens = self._get_num_tokens_by_gpt2(prompt_messages[0].content)
            completion_tokens = self._get_num_tokens_by_gpt2(assistant_message.content)
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )
        result = LLMResult(
            model=response_json["model"],
            prompt_messages=prompt_messages,
            message=assistant_message,
            usage=usage,
        )
        return result

    def _handle_tool_call_stream(self, chunk_json: dict, tool_calls_by_index: dict):
        """
        Handle tool call stream response using index-based aggregation (Tongyi-like).
        
        :param chunk_json: chunk json from Ollama response
        :param tool_calls_by_index: accumulated tool calls dict keyed by index
        """
        
        # normalize arguments to string for stability
        def _normalize_arguments(args):
            if args is None:
                return ""
            if isinstance(args, (dict, list)):
                try:
                    return json.dumps(args, ensure_ascii=False)
                except Exception as e:
                    logger.warning(f"Failed to serialize arguments to JSON: {e}")
                    return str(args)  # Fallback to string conversion
            return str(args)
        
        tool_calls_stream = chunk_json.get("message", {}).get("tool_calls")
        if not tool_calls_stream:
            return
        
        for tool_call_stream in tool_calls_stream:
            function_data = tool_call_stream.get("function", {})
            func_name = function_data.get("name")
            args_chunk = _normalize_arguments(function_data.get("arguments"))
            idx = tool_call_stream.get("index")
            # default to append order if index missing
            if not isinstance(idx, int):
                # place at next available position according to current max index
                if tool_calls_by_index:
                    idx = max(tool_calls_by_index.keys()) + 1
                else:
                    idx = 0

            # Prevent excessive index values from consuming memory
            if idx >= _MAX_TOOL_CALLS:
                logger.warning(f"Tool call index {idx} exceeds maximum allowed size {_MAX_TOOL_CALLS}.")
                continue

            # create new entry if it doesn't exist
            existing = tool_calls_by_index.get(idx)
            if existing is None:
                tc_id_value = tool_call_stream.get("id") or str(idx)
                tool_calls_by_index[idx] = AssistantPromptMessage.ToolCall(
                    id=tc_id_value,
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=func_name or "",
                        arguments=args_chunk,
                    ),
                )
            else:
                # merge into existing entry
                tool_call_obj = existing
                if func_name:
                    # overwrite name to avoid duplication
                    tool_call_obj.function.name = func_name
                if args_chunk:
                    tool_call_obj.function.arguments += args_chunk

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        completion_type: LLMMode,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        """
        Handle llm completion stream response

        :param model: model name
        :param credentials: model credentials
        :param completion_type: completion type
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator result
        """
        full_text = ""
        chunk_index = 0
        tool_calls_by_index = {}  # use dict aggregator to avoid sparse large lists
        tool_phase = False  # switch to delta-only text after detecting tool_calls
        micro_chunk_size = _MICRO_CHUNK_SIZE  # mimic pure text small increments
        is_reasoning_started = 0  # 0 not started, 1 started, 2 ended

        def _wrap_thinking_by_reasoning_content(message_obj: dict, is_reasoning: int) -> tuple[str, int]:
            """
            If the reasoning response is from message_obj.get("thinking"), we wrap
            it with HTML think tag.

            :param message_obj: message_obj dictionary from LLM streaming response
            :param is_reasoning: 0 not started, 1 started, 2 ended
            :return: tuple of (processed_content, is_reasoning)
            """

            content = message_obj.get("content") or ""
            thinking_content = message_obj.get("thinking")

            if thinking_content:
                if 0 == is_reasoning:
                    content = "<think>\n" + thinking_content
                    is_reasoning = 1
                elif 1 == is_reasoning:
                    content = thinking_content
                else:
                    logger.warning(f"Unexpected reasoning state is_reasoning: {is_reasoning} "
                                   f"content: {content} thinking_content: {thinking_content}")
            elif 1 == is_reasoning and content:
                content = "\n</think>" + content
                is_reasoning = 2
            return content, is_reasoning

        def _yield_micro_chunks(s: str, size: int, min_size: int = 4) -> list[str]:
            """
            Split by natural boundaries (spaces/newlines) to mimic pure text streaming.
            Group tokens to approx `size` without emitting chunks smaller than `min_size` (except for newlines).
            """
            parts: list[str] = []
            buffer = ""
            # Split into whitespace and non-whitespace tokens, preserving separators
            tokens = re.split(r"(\s+)", s)
            for tok in tokens:
                if not tok:
                    continue
                # If current token would exceed size and buffer is not empty, flush
                if buffer and len(buffer) + len(tok) > size:
                    parts.append(buffer)
                    buffer = tok
                else:
                    buffer += tok
                # Prefer to flush at newline boundaries for responsiveness (respect min_size)
                if "\n" in tok and len(buffer) >= max(min_size, size // 2):
                    parts.append(buffer)
                    buffer = ""
            if buffer:
                parts.append(buffer)
            return parts

        def create_final_llm_result_chunk(
            index: int, message: AssistantPromptMessage, finish_reason: str
        ) -> LLMResultChunk:
            prompt_tokens = self._get_num_tokens_by_gpt2(prompt_messages[0].content)
            completion_tokens = self._get_num_tokens_by_gpt2(full_text)
            usage = self._calc_response_usage(
                model, credentials, prompt_tokens, completion_tokens
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

        for chunk in response.iter_lines(decode_unicode=True, delimiter="\n"):
            if not chunk:
                continue
            try:
                chunk_json = json.loads(chunk)
            except json.JSONDecodeError:
                yield create_final_llm_result_chunk(
                    index=chunk_index,
                    message=AssistantPromptMessage(content=""),
                    finish_reason="Non-JSON encountered.",
                )
                chunk_index += 1
                break
            if completion_type is LLMMode.CHAT:
                if not chunk_json:
                    continue
                message_obj = chunk_json.get("message") or {}
                # Prefer incremental `response` for streaming; fallback to final `message.content`
                if chunk_json.get("response") is not None:
                    text = chunk_json.get("response", "")
                else:
                    text, is_reasoning_started = _wrap_thinking_by_reasoning_content(
                        message_obj, is_reasoning_started
                     )

                # If this chunk contains tool_calls, yield a dedicated tool_calls delta (like Tongyi)
                if "tool_calls" in message_obj and message_obj.get("tool_calls"):
                    self._handle_tool_call_stream(chunk_json, tool_calls_by_index)
                    logger.info("[Ollama] stream tool_calls detected: %s", message_obj.get("tool_calls"))
                    tool_phase = True
                    assistant_prompt_message = AssistantPromptMessage(content="")
                    if tool_calls_by_index:
                        assistant_prompt_message.tool_calls = [
                            tool_calls_by_index[i]
                            for i in sorted(tool_calls_by_index)
                            if tool_calls_by_index[i] is not None
                        ]
                    yield LLMResultChunk(
                        model=chunk_json.get("model", model or "default_model"),
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=chunk_index,
                            message=assistant_prompt_message,
                            finish_reason="tool_calls",
                        ),
                    )
                    chunk_index += 1
            else:
                if not chunk_json:
                    continue
                text = chunk_json.get("response", "")
                
            # normal text streaming: compute delta/full first, then micro-chunk uniformly
            if text:
                text_to_yield = ""
                if tool_phase:
                    # delta-only: only yield newly added part after tool_calls
                    if full_text and text.startswith(full_text):
                        text_to_yield = text[len(full_text):]
                        full_text = text
                    else:
                        # If startswith fails, find longest common prefix
                        common_prefix_len = 0
                        for i in range(min(len(full_text), len(text))):
                            if full_text[i] == text[i]:
                                common_prefix_len += 1
                            else:
                                break
                        text_to_yield = text[common_prefix_len:]
                        full_text = text
                else:
                    # pure text phase: yield text as-is
                    text_to_yield = text
                    full_text += text_to_yield

                if text_to_yield:
                    # Micro-chunk for finer granularity and consistent UX
                    for piece in _yield_micro_chunks(text_to_yield, micro_chunk_size):
                        if not piece:
                            continue
                        assistant_prompt_message = AssistantPromptMessage(content=piece)
                        yield LLMResultChunk(
                            model=chunk_json.get("model", model or "default_model"),
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=assistant_prompt_message,
                            ),
                        )
                        chunk_index += 1
            
            if chunk_json.get("done"):
                # compute usage and emit final chunk with finish_reason
                if "prompt_eval_count" in chunk_json:
                    prompt_tokens = chunk_json["prompt_eval_count"]
                else:
                    prompt_message_content = prompt_messages[0].content
                    if isinstance(prompt_message_content, str):
                        prompt_tokens = self._get_num_tokens_by_gpt2(
                            prompt_message_content
                        )
                    elif isinstance(prompt_message_content, list):
                        content_text = ""
                        for message_content in prompt_message_content:
                            if message_content.type == PromptMessageContentType.TEXT:
                                message_content = cast(
                                    TextPromptMessageContent, message_content
                                )
                                content_text += message_content.data
                        prompt_tokens = self._get_num_tokens_by_gpt2(content_text)
                completion_tokens = chunk_json.get(
                    "eval_count", self._get_num_tokens_by_gpt2(full_text)
                )
                usage = self._calc_response_usage(
                    model, credentials, prompt_tokens, completion_tokens
                )
                # final chunk: include finish_reason and usage, no extra tool_calls
                yield LLMResultChunk(
                    model=chunk_json.get("model", model or "default_model"),
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=chunk_index,
                        message=AssistantPromptMessage(content=""),
                        finish_reason="stop",
                        usage=usage,
                    ),
                )
                chunk_index += 1
                break
            

    def _convert_prompt_message_tool_to_dict(self, tool: PromptMessageTool) -> dict:
        """
        Convert PromptMessageTool to dict for Ollama API

        :param tool: tool
        :return: tool dict
        """
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dict for Ollama API

        :param message: prompt message
        :return: message dict
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            elif isinstance(message.content, list):
                text = ""
                images = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(
                            TextPromptMessageContent, message_content
                        )
                        text = message_content.data
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_content = cast(
                            ImagePromptMessageContent, message_content
                        )
                        image_data = re.sub(
                            "^data:image\\/[a-zA-Z]+;base64,", "", message_content.data
                        )
                        images.append(image_data)
                message_dict = {"role": "user", "content": text, "images": images}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {"role": "tool", "content": message.content}
            # 关联到具体的函数调用以符合 OpenAI/Ollama 规范
            if hasattr(message, "tool_call_id") and message.tool_call_id:
                message_dict["tool_call_id"] = message.tool_call_id
        else:
            raise ValueError(f"Got unknown type {message}")
        return message_dict

    def _num_tokens_from_messages(self, messages: list[PromptMessage]) -> int:
        """
        Calculate num tokens.

        :param messages: messages
        """
        num_tokens = 0
        messages_dict = [self._convert_prompt_message_to_dict(m) for m in messages]
        for message in messages_dict:
            for key, value in message.items():
                num_tokens += self._get_num_tokens_by_gpt2(str(key))
                num_tokens += self._get_num_tokens_by_gpt2(str(value))
        return num_tokens

    def _extract_response_tool_call(
        self, response_tool_call: dict
    ) -> AssistantPromptMessage.ToolCall:
        """
        Extract response tool call
        """
        tool_call = None
        if response_tool_call and "function" in response_tool_call:
            arguments = response_tool_call.get("function", {}).get("arguments")
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments)
            function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                name=response_tool_call.get("function", {}).get("name"),
                arguments=arguments,
            )
            tool_call = AssistantPromptMessage.ToolCall(
                id=response_tool_call.get("function", {}).get("name"),
                type="function",
                function=function,
            )
        return tool_call

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        Get customizable model schema.

        :param model: model name
        :param credentials: credentials

        :return: model schema
        """
        # Build features from credentials and pass into AIModelEntity
        features: list[ModelFeature] = []
        if credentials.get("vision_support") == "true":
            features.append(ModelFeature.VISION)
        # 支持 true/supported/yes/1 形式开启函数调用
        fc_supported = str(credentials.get("function_call_support", "")).lower() in _TRUTHY_VALUES
        if fc_supported:
            features.append(ModelFeature.TOOL_CALL)
            features.append(ModelFeature.MULTI_TOOL_CALL)
            # 说明：Dify 的 Ollama 配置页没有单独的 stream_function_calling 项；
            # 若支持 function_call，则默认也支持流式工具调用（如需关闭，可在凭据中显式提供 false）。
            stream_fc_cfg = credentials.get("stream_function_calling")
            if stream_fc_cfg is None:
                features.append(ModelFeature.STREAM_TOOL_CALL)
            else:
                if str(stream_fc_cfg).lower() in _TRUTHY_VALUES:
                    features.append(ModelFeature.STREAM_TOOL_CALL)
        entity = AIModelEntity(
            model=model,
            label=I18nObject(zh_Hans=model, en_US=model),
            model_type=ModelType.LLM,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: credentials.get("mode"),
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 4096)
                ),
            },
            parameter_rules=[
                ParameterRule(
                    name=DefaultParameterName.TEMPERATURE.value,
                    use_template=DefaultParameterName.TEMPERATURE.value,
                    label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name=DefaultParameterName.TOP_P.value,
                    use_template=DefaultParameterName.TOP_P.value,
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                    type=ParameterType.FLOAT,
                    help=I18nObject(
                        en_US="Works together with top-k. A higher value (e.g., 0.95) will lead to more diverse text, while a lower value (e.g., 0.5) will generate more focused and conservative text. (Default: 0.9)",
                        zh_Hans="与top-k一起工作。较高的值（例如，0.95）会导致生成更多样化的文本，而较低的值（例如，0.5）会生成更专注和保守的文本。（默认值：0.9）",
                    ),
                    default=0.9,
                    min=0,
                    max=1,
                ),
                ParameterRule(
                    name="top_k",
                    label=I18nObject(en_US="Top K", zh_Hans="Top K"),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Reduces the probability of generating nonsense. A higher value (e.g. 100) will give more diverse answers, while a lower value (e.g. 10) will be more conservative. (Default: 40)",
                        zh_Hans="减少生成无意义内容的可能性。较高的值（例如100）将提供更多样化的答案，而较低的值（例如10）将更为保守。（默认值：40）",
                    ),
                    min=1,
                    max=100,
                ),
                ParameterRule(
                    name="repeat_penalty",
                    label=I18nObject(en_US="Repeat Penalty"),
                    type=ParameterType.FLOAT,
                    help=I18nObject(
                        en_US="Sets how strongly to penalize repetitions. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient. (Default: 1.1)",
                        zh_Hans="设置对重复内容的惩罚强度。一个较高的值（例如，1.5）会更强地惩罚重复内容，而一个较低的值（例如，0.9）则会相对宽容。（默认值：1.1）",
                    ),
                    min=-2,
                    max=2,
                ),
                ParameterRule(
                    name="num_predict",
                    use_template="max_tokens",
                    label=I18nObject(en_US="Num Predict", zh_Hans="最大令牌数预测"),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Maximum number of tokens to predict when generating text. (Default: 128, -1 = infinite generation, -2 = fill context)",
                        zh_Hans="生成文本时预测的最大令牌数。（默认值：128，-1 = 无限生成，-2 = 填充上下文）",
                    ),
                    default=512
                    if int(credentials.get("max_tokens", 4096)) >= 768
                    else 128,
                    min=-2,
                    max=int(credentials.get("max_tokens", 4096)),
                ),
                ParameterRule(
                    name="mirostat",
                    label=I18nObject(
                        en_US="Mirostat sampling", zh_Hans="Mirostat 采样"
                    ),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Enable Mirostat sampling for controlling perplexity. (default: 0, 0 = disabled, 1 = Mirostat, 2 = Mirostat 2.0)",
                        zh_Hans="启用 Mirostat 采样以控制困惑度。（默认值：0，0 = 禁用，1 = Mirostat，2 = Mirostat 2.0）",
                    ),
                    min=0,
                    max=2,
                ),
                ParameterRule(
                    name="mirostat_eta",
                    label=I18nObject(en_US="Mirostat Eta", zh_Hans="学习率"),
                    type=ParameterType.FLOAT,
                    help=I18nObject(
                        en_US="Influences how quickly the algorithm responds to feedback from the generated text. A lower learning rate will result in slower adjustments, while a higher learning rate will make the algorithm more responsive. (Default: 0.1)",
                        zh_Hans="影响算法对生成文本反馈响应的速度。较低的学习率会导致调整速度变慢，而较高的学习率会使得算法更加灵敏。（默认值：0.1）",
                    ),
                    precision=1,
                ),
                ParameterRule(
                    name="mirostat_tau",
                    label=I18nObject(en_US="Mirostat Tau", zh_Hans="文本连贯度"),
                    type=ParameterType.FLOAT,
                    help=I18nObject(
                        en_US="Controls the balance between coherence and diversity of the output. A lower value will result in more focused and coherent text. (Default: 5.0)",
                        zh_Hans="控制输出的连贯性和多样性之间的平衡。较低的值会导致更专注和连贯的文本。（默认值：5.0）",
                    ),
                    precision=1,
                ),
                ParameterRule(
                    name="num_ctx",
                    label=I18nObject(
                        en_US="Size of context window", zh_Hans="上下文窗口大小"
                    ),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Sets the size of the context window used to generate the next token. (Default: 2048)",
                        zh_Hans="设置用于生成下一个标记的上下文窗口大小。（默认值：2048）",
                    ),
                    default=2048,
                    min=1,
                ),
                ParameterRule(
                    name="num_gpu",
                    label=I18nObject(en_US="GPU Layers", zh_Hans="GPU 层数"),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="The number of layers to offload to the GPU(s). On macOS it defaults to 1 to enable metal support, 0 to disable.As long as a model fits into one gpu it stays in one. It does not set the number of GPU(s). ",
                        zh_Hans="加载到 GPU 的层数。在 macOS 上，默认为 1 以启用 Metal 支持，设置为 0 则禁用。只要模型适合一个 GPU，它就保留在其中。它不设置 GPU 的数量。",
                    ),
                    min=-1,
                    default=1,
                ),
                ParameterRule(
                    name="num_thread",
                    label=I18nObject(en_US="Num Thread", zh_Hans="线程数"),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Sets the number of threads to use during computation. By default, Ollama will detect this for optimal performance. It is recommended to set this value to the number of physical CPU cores your system has (as opposed to the logical number of cores).",
                        zh_Hans="设置计算过程中使用的线程数。默认情况下，Ollama会检测以获得最佳性能。建议将此值设置为系统拥有的物理CPU核心数（而不是逻辑核心数）。",
                    ),
                    min=1,
                ),
                ParameterRule(
                    name="repeat_last_n",
                    label=I18nObject(en_US="Repeat last N", zh_Hans="回溯内容"),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Sets how far back for the model to look back to prevent repetition. (Default: 64, 0 = disabled, -1 = num_ctx)",
                        zh_Hans="设置模型回溯多远的内容以防止重复。（默认值：64，0 = 禁用，-1 = num_ctx）",
                    ),
                    min=-1,
                ),
                ParameterRule(
                    name="tfs_z",
                    label=I18nObject(en_US="TFS Z", zh_Hans="减少标记影响"),
                    type=ParameterType.FLOAT,
                    help=I18nObject(
                        en_US="Tail free sampling is used to reduce the impact of less probable tokens from the output. A higher value (e.g., 2.0) will reduce the impact more, while a value of 1.0 disables this setting. (default: 1)",
                        zh_Hans="用于减少输出中不太可能的标记的影响。较高的值（例如，2.0）会更多地减少这种影响，而1.0的值则会禁用此设置。（默认值：1）",
                    ),
                    precision=1,
                ),
                ParameterRule(
                    name="seed",
                    label=I18nObject(en_US="Seed", zh_Hans="随机数种子"),
                    type=ParameterType.INT,
                    help=I18nObject(
                        en_US="Sets the random number seed to use for generation. Setting this to a specific number will make the model generate the same text for the same prompt. (Default: 0)",
                        zh_Hans="设置用于生成的随机数种子。将此设置为特定数字将使模型对相同的提示生成相同的文本。（默认值：0）",
                    ),
                ),
                ParameterRule(
                    name="keep_alive",
                    label=I18nObject(en_US="Keep Alive", zh_Hans="模型存活时间"),
                    type=ParameterType.STRING,
                    help=I18nObject(
                        en_US="Sets how long the model is kept in memory after generating a response. This must be a duration string with a unit (e.g., '10m' for 10 minutes or '24h' for 24 hours). A negative number keeps the model loaded indefinitely, and '0' unloads the model immediately after generating a response. Valid time units are 's','m','h'. (Default: 5m)",
                        zh_Hans="设置模型在生成响应后在内存中保留的时间。这必须是一个带有单位的持续时间字符串（例如，'10m' 表示10分钟，'24h' 表示24小时）。负数表示无限期地保留模型，'0'表示在生成响应后立即卸载模型。有效的时间单位有 's'（秒）、'm'（分钟）、'h'（小时）。（默认值：5m）",
                    ),
                ),
                ParameterRule(
                    name="format",
                    label=I18nObject(en_US="Format", zh_Hans="返回格式"),
                    type=ParameterType.STRING,
                    help=I18nObject(
                        en_US="the format to return a response in. Currently the only accepted value is json.",
                        zh_Hans="返回响应的格式。目前唯一接受的值是json。",
                    ),
                    options=["json"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema", zh_Hans="JSON Schema"),
                    type=ParameterType.STRING,
                    help=I18nObject(
                        en_US="Return output in the format defined by JSON Schema.",
                        zh_Hans="按照JSON Schema定义的格式返回output",
                    ),
                ),
                ParameterRule(
                    name="think",
                    label=I18nObject(en_US="Think", zh_Hans="思考模式"),
                    type=ParameterType.BOOLEAN,
                    help=I18nObject(
                        en_US="Enable thinking mode where the model thinks before responding.",
                        zh_Hans="启用思考模式，模型在响应前会先进行思考。",
                    ),
                ),
            ],
            pricing=PriceConfig(
                input=Decimal(credentials.get("input_price", 0)),
                output=Decimal(credentials.get("output_price", 0)),
                unit=Decimal(credentials.get("unit", 0)),
                currency=credentials.get("currency", "USD"),
            ),
            features=features,
        )
        return entity

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
            InvokeAuthorizationError: [requests.exceptions.InvalidHeader],
            InvokeBadRequestError: [
                requests.exceptions.HTTPError,
                requests.exceptions.InvalidURL,
            ],
            InvokeRateLimitError: [requests.exceptions.RetryError],
            InvokeServerUnavailableError: [
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
            ],
            InvokeConnectionError: [
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ReadTimeout,
            ],
        }
