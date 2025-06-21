from collections.abc import Generator
from json import dumps, loads
from typing import Any, Union
from requests import Response, post
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
    Minimax Chat Completion V2 API, supports OpenAI-compatible format
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
        generate chat completion using v2 API
        """
        if not api_key or not group_id:
            raise InvalidAPIKeyError("Invalid API key or group ID")

        # Remove trailing slash and construct URL
        base_url = endpoint_url.rstrip('/')
        url = f"{base_url}/v1/text/chatcompletion_v2"

        # Build request parameters
        extra_kwargs = {}
        if "max_tokens" in model_parameters and isinstance(
            model_parameters["max_tokens"], int
        ):
            extra_kwargs["max_tokens"] = model_parameters["max_tokens"]
        if "temperature" in model_parameters and isinstance(
            model_parameters["temperature"], (int, float)
        ):
            extra_kwargs["temperature"] = float(
                model_parameters["temperature"]
            )
        if "top_p" in model_parameters and isinstance(
            model_parameters["top_p"], (int, float)
        ):
            extra_kwargs["top_p"] = float(model_parameters["top_p"])
        if "top_k" in model_parameters and isinstance(
            model_parameters["top_k"], int
        ):
            extra_kwargs["top_k"] = model_parameters["top_k"]
        if "presence_penalty" in model_parameters and isinstance(
            model_parameters["presence_penalty"], (int, float)
        ):
            extra_kwargs["presence_penalty"] = float(
                model_parameters["presence_penalty"]
            )
        if "frequency_penalty" in model_parameters and isinstance(
            model_parameters["frequency_penalty"], (int, float)
        ):
            extra_kwargs["frequency_penalty"] = float(
                model_parameters["frequency_penalty"]
            )

        if len(prompt_messages) == 0:
            raise BadRequestError("At least one message is required")

        # Check if at least one user message exists, if not, add one
        has_user_message = any(
            message.role == MinimaxMessage.Role.USER.value
            for message in prompt_messages
        )
        if not has_user_message:
            # Add an empty user message
            user_message = MinimaxMessage(
                content="",
                role=MinimaxMessage.Role.USER.value
            )
            prompt_messages.append(user_message)

        # Convert messages to OpenAI-compatible format
        messages = []
        for message in prompt_messages:
            # Map MinimaxMessage roles to API expected roles
            role_mapping = {
                MinimaxMessage.Role.USER.value: "user",          # "USER" -> "user"
                MinimaxMessage.Role.ASSISTANT.value: "assistant",  # "BOT" -> "assistant"
                MinimaxMessage.Role.SYSTEM.value: "system",      # "SYSTEM" -> "system"
                MinimaxMessage.Role.FUNCTION.value: "tool",      # "FUNCTION" -> "tool"
            }

            api_role = role_mapping.get(message.role, message.role.lower())

            # Ensure content is not None - MiniMax API requires string content
            content = message.content if message.content is not None else ""

            msg_dict = {
                "role": api_role,
                "content": content
            }

            # Handle assistant message with function call
            if message.role == MinimaxMessage.Role.ASSISTANT.value and message.function_call:
                # Convert function_call to tool_calls format
                msg_dict["tool_calls"] = [{
                    "id": f"call_function_{hash(message.function_call['name']) % 10000000000}",
                    "type": "function",
                    "function": {
                        "name": message.function_call["name"],
                        "arguments": message.function_call["arguments"]
                    }
                }]
                # For function call messages, content can be empty
                msg_dict["content"] = content

            # Handle tool message - need tool_call_id
            elif api_role == "tool":
                # Tool messages should have tool_call_id, but we don't have it in MinimaxMessage
                # For compatibility, we'll use a generated ID
                msg_dict["tool_call_id"] = f"call_function_{hash(message.content) % 10000000000}"

            messages.append(msg_dict)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        body = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **extra_kwargs,
        }

        # Add tools if provided
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"]
                    }
                } for tool in tools
            ]
            body["tool_choice"] = "auto"

        # Add stop sequences if provided
        if stop:
            body["stop"] = stop

        try:
            response = post(
                url=url,
                data=dumps(body),
                headers=headers,
                stream=stream,
                timeout=(10, 300)
            )
        except Exception as e:
            raise InternalServerError(str(e))

        if response.status_code != 200:
            error_text = response.text
            try:
                error_json = loads(error_text)
                if "error" in error_json:
                    error_msg = error_json["error"].get("message", error_text)
                    error_code = error_json["error"].get("code", "unknown")
                    self._handle_error_by_message(error_msg, error_code)
                else:
                    raise InternalServerError(error_text)
            except (ValueError, KeyError):
                raise InternalServerError(error_text)

        if stream:
            return self._handle_stream_chat_generate_response(response)
        return self._handle_chat_generate_response(response)

    def _wrap_thinking_by_reasoning_content(self, message_data: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        Handle reasoning_content in MiniMax response format
        :param message_data: message data from API response
        :param is_reasoning: current reasoning state
        :return: tuple of (processed_content, is_reasoning)
        """
        content = message_data.get("content") or ""
        reasoning_content = message_data.get("reasoning_content")

        try:
            if reasoning_content:
                # Convert reasoning_content to string if needed
                if isinstance(reasoning_content, list):
                    reasoning_content = "\n".join(map(str, reasoning_content))
                elif not isinstance(reasoning_content, str):
                    reasoning_content = str(reasoning_content)

                if not is_reasoning:
                    # Start reasoning block
                    content = "<think>\n" + reasoning_content
                    is_reasoning = True
                else:
                    # Continue reasoning block
                    content = reasoning_content
            elif is_reasoning and content:
                # End reasoning block and start normal content
                if not isinstance(content, str):
                    content = str(content)
                content = "\n</think>\n\n" + content
                is_reasoning = False
        except Exception as ex:
            raise ValueError(f"[wrap_thinking_by_reasoning_content] {ex}") from ex

        return content, is_reasoning

    def _handle_error_by_message(self, message: str, code: str):
        """Handle error based on error message and code"""
        message_lower = message.lower()
        if "unauthorized" in message_lower or "invalid api key" in message_lower:
            raise InvalidAuthenticationError(message)
        elif "insufficient" in message_lower and "balance" in message_lower:
            raise InsufficientAccountBalanceError(message)
        elif "rate limit" in message_lower or "too many requests" in message_lower:
            raise RateLimitReachedError(message)
        elif "bad request" in message_lower or "invalid" in message_lower:
            raise BadRequestError(message)
        else:
            raise InternalServerError(message)

    def _handle_error_by_code(self, code: int, msg: str):
        """Handle error based on Minimax error code"""
        if code in {1000, 1001, 1013, 1027}:
            raise InternalServerError(msg)
        elif code in {1002, 1039}:
            raise RateLimitReachedError(msg)
        elif code == 1004:
            raise InvalidAuthenticationError(msg)
        elif code == 1008:
            raise InsufficientAccountBalanceError(msg)
        elif code == 2013:
            raise BadRequestError(msg)
        else:
            raise InternalServerError(msg)

    def _handle_chat_generate_response(self, response: Response) -> MinimaxMessage:
        """
        handle chat generate response for non-streaming
        """
        response_json = response.json()

        # Check for Minimax-specific error format first
        if "base_resp" in response_json and response_json["base_resp"]["status_code"] != 0:
            code = response_json["base_resp"]["status_code"]
            msg = response_json["base_resp"]["status_msg"]
            self._handle_error_by_code(code, msg)

        # Check for OpenAI-style error format
        if "error" in response_json:
            error_info = response_json["error"]
            error_msg = error_info.get("message", "Unknown error")
            error_code = error_info.get("code", "unknown")
            self._handle_error_by_message(error_msg, error_code)

        # Extract the response content
        choices = response_json.get("choices", [])
        if not choices:
            raise InternalServerError(f"No choices in response: {response_json}")

        choice = choices[0]
        message_content = choice.get("message", {})

        # Handle reasoning_content and normal content
        is_reasoning = False
        processed_content, _ = self._wrap_thinking_by_reasoning_content(message_content, is_reasoning)

        # If we have reasoning_content, we might need to close the thinking block
        if message_content.get("reasoning_content") and message_content.get("content"):
            # We have both reasoning and normal content, close the thinking block
            content = message_content.get("content", "")
            if processed_content.startswith("<think>"):
                processed_content = processed_content + "\n</think>\n\n" + content
            else:
                processed_content = content
        elif not processed_content:
            # Fallback to original content
            processed_content = message_content.get("content", "")

        # Create MinimaxMessage with assistant role
        message = MinimaxMessage(
            content=processed_content,
            role=MinimaxMessage.Role.ASSISTANT.value
        )

        # Handle tool calls
        tool_calls = message_content.get("tool_calls")
        if tool_calls:
            # Convert tool calls to function call format for compatibility
            if tool_calls and len(tool_calls) > 0:
                first_tool_call = tool_calls[0]
                if first_tool_call.get("type") == "function":
                    function_info = first_tool_call.get("function", {})
                    message.function_call = {
                        "name": function_info.get("name", ""),
                        "arguments": function_info.get("arguments", "{}")
                    }

        # Extract usage information
        usage_info = response_json.get("usage", {})
        if usage_info:
            # Ensure prompt_tokens and completion_tokens are properly set
            prompt_tokens = usage_info.get("prompt_tokens", 0)
            total_tokens = usage_info.get("total_tokens", 0)
            completion_tokens = usage_info.get("completion_tokens", total_tokens - prompt_tokens)

            message.usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }

        # Set stop reason
        message.stop_reason = choice.get("finish_reason", "")

        return message

    def _handle_stream_chat_generate_response(
        self, response: Response
    ) -> Generator[MinimaxMessage, None, None]:
        """
        handle stream chat generate response
        """
        is_reasoning = False

        for line in response.iter_lines():
            if not line:
                continue

            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                line_str = line_str[6:].strip()

            if line_str == "[DONE]":
                break

            try:
                data = loads(line_str)
            except ValueError:
                continue

            # Check for errors
            if "base_resp" in data and data["base_resp"]["status_code"] != 0:
                code = data["base_resp"]["status_code"]
                msg = data["base_resp"]["status_msg"]
                self._handle_error_by_code(code, msg)

            if "error" in data:
                error_info = data["error"]
                error_msg = error_info.get("message", "Unknown error")
                error_code = error_info.get("code", "unknown")
                self._handle_error_by_message(error_msg, error_code)

            choices = data.get("choices", [])
            if not choices:
                continue

            choice = choices[0]

            # Handle delta chunks (streaming content)
            if "delta" in choice:
                delta = choice["delta"]

                # Process reasoning_content and content with thinking wrapper
                processed_content, is_reasoning = self._wrap_thinking_by_reasoning_content(delta, is_reasoning)

                if processed_content:
                    yield MinimaxMessage(
                        content=processed_content,
                        role=MinimaxMessage.Role.ASSISTANT.value
                    )

                # Handle tool calls delta
                tool_calls = delta.get("tool_calls")
                if tool_calls:
                    for tool_call in tool_calls:
                        if tool_call.get("type") == "function":
                            function_info = tool_call.get("function", {})
                            function_call_message = MinimaxMessage(
                                content="",
                                role=MinimaxMessage.Role.ASSISTANT.value
                            )
                            function_call_message.function_call = {
                                "name": function_info.get("name", ""),
                                "arguments": function_info.get("arguments", "{}")
                            }
                            yield function_call_message

            # Handle final message chunk (contains usage and final message)
            elif "message" in choice:
                message_data = choice["message"]

                # Handle tool calls in final message
                tool_calls = message_data.get("tool_calls")
                if tool_calls:
                    for tool_call in tool_calls:
                        if tool_call.get("type") == "function":
                            function_info = tool_call.get("function", {})
                            function_call_message = MinimaxMessage(
                                content="",
                                role=MinimaxMessage.Role.ASSISTANT.value
                            )
                            function_call_message.function_call = {
                                "name": function_info.get("name", ""),
                                "arguments": function_info.get("arguments", "{}")
                            }
                            yield function_call_message

                # Handle usage info in final chunk
                usage_info = data.get("usage", {})
                if usage_info:
                    prompt_tokens = usage_info.get("prompt_tokens", 0)
                    total_tokens = usage_info.get("total_tokens", 0)
                    completion_tokens = usage_info.get("completion_tokens", total_tokens - prompt_tokens)

                    usage_message = MinimaxMessage(
                        content="",
                        role=MinimaxMessage.Role.ASSISTANT.value
                    )
                    usage_message.usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    }
                    usage_message.stop_reason = choice.get("finish_reason", "")
                    yield usage_message
