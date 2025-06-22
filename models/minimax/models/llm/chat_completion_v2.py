from collections.abc import Generator
from json import dumps, loads
from typing import Any, Union
from requests import Response, post
import logging
from models.llm.errors import (
    BadRequestError,
    InsufficientAccountBalanceError,
    InternalServerError,
    InvalidAPIKeyError,
    InvalidAuthenticationError,
    RateLimitReachedError,
)
from models.llm.types import MinimaxMessage


class MinimaxChatCompletionV2:
    """
    Minimax Chat Completion V2 API
    Supports OpenAI compatible format and multi-tool calling
    """

    def generate(
        self,
        model: str,
        api_key: str,
        group_id: str,
        endpoint_url: str,
        prompt_messages: list[MinimaxMessage],
        model_parameters: dict,
        tools: list[dict[str, Any]],
        stop: list[str] | None,
        stream: bool,
        user: str,
    ) -> Union[MinimaxMessage, Generator[MinimaxMessage, None, None]]:
        """
        Call MiniMax v2 API to generate response
        """
        if not api_key:
            raise InvalidAPIKeyError("API key is required")

        # 构建请求 URL
        base_url = endpoint_url.rstrip('/')
        url = f"{base_url}/v1/text/chatcompletion_v2"

        # 准备请求头
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 构建请求体
        body = self._build_request_body(
            model, prompt_messages, model_parameters, tools, stop, stream
        )

        # 发送请求
        try:
            response = post(
                url=url,
                data=dumps(body),
                headers=headers,
                stream=stream,
                timeout=(10, 300)
            )
        except Exception as e:
            raise InternalServerError(f"Request failed: {str(e)}")

        # 处理响应
        if response.status_code != 200:
            self._handle_error_response(response)

        if stream:
            return self._handle_stream_response(response)
        else:
            return self._handle_non_stream_response(response)

    def _build_request_body(
        self,
        model: str,
        prompt_messages: list[MinimaxMessage],
        model_parameters: dict,
        tools: list[dict[str, Any]],
        stop: list[str] | None,
        stream: bool
    ) -> dict:
        """Build request body"""
        # Convert message format
        messages = self._convert_messages(prompt_messages)

        # Basic request body
        body = {
            "model": model,
            "messages": messages,
            "stream": stream
        }

        # Add model parameters
        if "max_tokens" in model_parameters:
            body["max_tokens"] = int(model_parameters["max_tokens"])
        if "temperature" in model_parameters:
            body["temperature"] = float(model_parameters["temperature"])
        if "top_p" in model_parameters:
            body["top_p"] = float(model_parameters["top_p"])
        if "top_k" in model_parameters:
            body["top_k"] = int(model_parameters["top_k"])
        if "presence_penalty" in model_parameters:
            body["presence_penalty"] = float(model_parameters["presence_penalty"])
        if "frequency_penalty" in model_parameters:
            body["frequency_penalty"] = float(model_parameters["frequency_penalty"])

        # Add tools
        if tools:
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            } for tool in tools]
            body["tool_choice"] = "auto"

        # Add stop sequences
        if stop:
            body["stop"] = stop

        return body

    def _convert_messages(self, prompt_messages: list[MinimaxMessage]) -> list[dict]:
        """Convert message format to API required format"""
        messages = []

        for message in prompt_messages:
            # Role mapping
            role_mapping = {
                "USER": "user",
                "BOT": "assistant",
                "SYSTEM": "system",
                "FUNCTION": "tool"
            }

            msg_dict = {
                "role": role_mapping.get(message.role, "user"),
                "content": message.content or ""
            }

            # Handle tool calls in assistant messages
            if message.role == "BOT" and message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": tc.get("type", "function"),
                        "function": tc.get("function", {})
                    }
                    for tc in message.tool_calls
                ]

            # Handle tool response messages
            if msg_dict["role"] == "tool" and message.tool_call_id:
                msg_dict["tool_call_id"] = message.tool_call_id

            messages.append(msg_dict)

        return messages

    def _handle_error_response(self, response: Response):
        """Handle error response"""
        try:
            error_data = response.json()
        except (ValueError, Exception):
            raise InternalServerError(f"Invalid response: {response.text}")

        # 处理标准错误格式
        if "error" in error_data:
            error = error_data["error"]
            message = error.get("message", "Unknown error")

            if "unauthorized" in message.lower() or "invalid api key" in message.lower():
                raise InvalidAuthenticationError(message)
            elif "insufficient" in message.lower() and "balance" in message.lower():
                raise InsufficientAccountBalanceError(message)
            elif "rate limit" in message.lower():
                raise RateLimitReachedError(message)
            elif "tool call id is invalid" in message.lower():
                raise BadRequestError(f"Invalid tool call ID: {message}")
            else:
                raise InternalServerError(message)

        # 处理 MiniMax 特定错误格式
        if "base_resp" in error_data and error_data["base_resp"]["status_code"] != 0:
            status_code = error_data["base_resp"]["status_code"]
            status_msg = error_data["base_resp"]["status_msg"]

            error_mapping = {
                1000: InternalServerError,
                1001: InternalServerError,
                1002: RateLimitReachedError,
                1004: InvalidAuthenticationError,
                1008: InsufficientAccountBalanceError,
                1013: InternalServerError,
                1027: InternalServerError,
                1039: RateLimitReachedError,
                2013: BadRequestError
            }

            error_class = error_mapping.get(status_code, InternalServerError)
            raise error_class(status_msg)

        raise InternalServerError(f"Unknown error: {response.text}")

    def _handle_non_stream_response(self, response: Response) -> MinimaxMessage:
        """Handle non-stream response"""
        data = response.json()

        # 检查错误
        if "error" in data:
            self._handle_error_response(response)

        # 提取响应内容
        choices = data.get("choices", [])
        if not choices:
            raise InternalServerError("No choices in response")

        choice = choices[0]
        message_data = choice.get("message", {})

        # Process content and reasoning chain
        content = self._process_content_with_reasoning(message_data)

        # 创建响应消息
        result_message = MinimaxMessage(
            content=content,
            role="BOT"
        )

        # 处理工具调用
        if message_data.get("tool_calls"):
            result_message.tool_calls = message_data["tool_calls"]

        # 添加使用信息
        usage = data.get("usage", {})
        if usage:
            result_message.usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }

        # 添加停止原因
        result_message.stop_reason = choice.get("finish_reason", "")

        return result_message

    def _handle_stream_response(
        self, response: Response
    ) -> Generator[MinimaxMessage, None, None]:
        """Handle stream response"""
        is_reasoning = False
        tool_call_chunks = {}  # Used to accumulate tool call information
        has_reasoning_content = False  # Whether there is reasoning content

        for line in response.iter_lines():
            if not line:
                continue

            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                line_str = line_str[6:].strip()

            if line_str == "[DONE]":
                # Check if there are unprocessed tool calls
                if tool_call_chunks:
                    # Process remaining tool calls
                    valid_tool_calls = []
                    for index in sorted(tool_call_chunks.keys()):
                        tc = tool_call_chunks[index]
                        if tc.get("id") and tc.get("function", {}).get("name"):
                            valid_tool_calls.append(tc)

                    if valid_tool_calls:
                        # If reasoning is still in progress, end reasoning first
                        if is_reasoning:
                            yield MinimaxMessage(content="\n</think>\n\n", role="BOT")
                            is_reasoning = False

                        tool_message = MinimaxMessage(content="", role="BOT")
                        tool_message.tool_calls = valid_tool_calls
                        yield tool_message
                elif is_reasoning:
                    # If reasoning is still in progress, close the reasoning tag
                    yield MinimaxMessage(content="\n</think>\n\n", role="BOT")
                break

            try:
                data = loads(line_str)
            except (ValueError, Exception):
                continue

            # 检查错误
            if "error" in data:
                self._handle_error_response(response)

            choices = data.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})

            finish_reason = choice.get("finish_reason")

            # Process content and reasoning content
            if "content" in delta or "reasoning_content" in delta:
                if "reasoning_content" in delta:
                    has_reasoning_content = True

                content, is_reasoning = self._process_delta_with_reasoning(
                    delta, is_reasoning
                )

                if content:
                    yield MinimaxMessage(content=content, role="BOT")

            # Accumulate tool call information
            if "tool_calls" in delta:
                for tool_call in delta["tool_calls"]:
                    index = tool_call.get("index", 0)

                    if index not in tool_call_chunks:
                        tool_call_chunks[index] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        }

                    # Accumulate tool call information
                    if "id" in tool_call:
                        tool_call_chunks[index]["id"] = tool_call["id"]
                    if "type" in tool_call:
                        tool_call_chunks[index]["type"] = tool_call["type"]
                    if "function" in tool_call:
                        func = tool_call["function"]
                        if "name" in func:
                            tool_call_chunks[index]["function"]["name"] = func["name"]
                        if "arguments" in func:
                            tool_call_chunks[index]["function"]["arguments"] += func["arguments"]

            # Check if tool call is completed
            if finish_reason == "tool_calls":
                # If there is reasoning content but not properly ended, end reasoning first
                if has_reasoning_content and is_reasoning:
                    yield MinimaxMessage(content="\n</think>\n\n", role="BOT")
                    is_reasoning = False

                # Build complete tool call list, filter out invalid tool calls
                valid_tool_calls = []
                for index in sorted(tool_call_chunks.keys()):
                    tc = tool_call_chunks[index]
                    # Ensure tool call is valid (must have ID and function name)
                    if tc.get("id") and tc.get("function", {}).get("name"):
                        valid_tool_calls.append(tc)

                # Only return when there are valid tool calls
                if valid_tool_calls:
                    tool_message = MinimaxMessage(content="", role="BOT")
                    tool_message.tool_calls = valid_tool_calls
                    yield tool_message

                # Clear accumulated tool calls
                tool_call_chunks = {}

            # Process usage information (last chunk)
            if "usage" in data and data["usage"]:
                usage_message = MinimaxMessage(content="", role="BOT")
                usage_message.usage = {
                    "prompt_tokens": data["usage"].get("prompt_tokens", 0),
                    "completion_tokens": data["usage"].get("completion_tokens", 0),
                    "total_tokens": data["usage"].get("total_tokens", 0)
                }
                usage_message.stop_reason = choice.get("finish_reason", "")
                yield usage_message

            # Process complete message (for cases where tool_calls might be in message)
            if "message" in choice:
                message_data = choice["message"]
                if message_data.get("tool_calls") and not tool_call_chunks:
                    # If reasoning is still in progress, end reasoning first
                    if is_reasoning:
                        yield MinimaxMessage(content="\n</think>\n\n", role="BOT")
                        is_reasoning = False

                    tool_message = MinimaxMessage(content="", role="BOT")
                    tool_message.tool_calls = message_data["tool_calls"]
                    yield tool_message

    def _process_content_with_reasoning(self, message_data: dict) -> str:
        """Process message containing reasoning content"""
        content = message_data.get("content", "")
        reasoning_content = message_data.get("reasoning_content")

        if reasoning_content:
            # Wrap reasoning content in thinking tags
            if isinstance(reasoning_content, list):
                reasoning_content = "\n".join(map(str, reasoning_content))

            if content:
                # Has both reasoning content and normal content - complete thinking chain format
                return f"<think>\n{reasoning_content}\n</think>\n\n{content}"
            else:
                # Only has reasoning content - might have subsequent tool calls, don't close yet
                return f"<think>\n{reasoning_content}\n</think>"

        return content

    def _process_delta_with_reasoning(
        self, delta: dict, is_reasoning: bool
    ) -> tuple[str, bool]:
        """Process reasoning content in stream response"""
        content = delta.get("content", "")
        reasoning_content = delta.get("reasoning_content")

        if reasoning_content:
            if isinstance(reasoning_content, list):
                reasoning_content = "\n".join(map(str, reasoning_content))

            if not is_reasoning:
                # Start reasoning
                return f"<think>\n{reasoning_content}", True
            else:
                # Continue reasoning
                return reasoning_content, True
        elif content:
            if is_reasoning:
                # Reasoning ends, has normal content - close thinking chain
                return f"\n</think>\n\n{content}", False
            else:
                # Normal content
                return content, False
        else:
            # No content, maintain current state
            return "", is_reasoning
