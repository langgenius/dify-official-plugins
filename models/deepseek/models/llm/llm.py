import json
import re
from collections.abc import Generator
from html import escape, unescape

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageFunction,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from models.llm._metadata import apply_dify_headers_if_enabled
from requests import Response


class _StreamResponse:
    """Observe DeepSeek extensions while leaving SSE handling to the SDK."""

    def __init__(self, response: Response):
        self.response = response
        self.metadata: dict = {}

    def iter_lines(self, **kwargs):
        reasoning = ""
        for line in self.response.iter_lines(**kwargs):
            try:
                chunk = json.loads(line.strip().removeprefix("data:").lstrip())
            except (ValueError, TypeError):
                yield line
                continue
            if not isinstance(chunk, dict):
                yield line
                continue
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta", {})
                reasoning += delta.get("reasoning_content") or ""
                event = choice.get("server_tool_event") or {}
                if event.get("type") == "step_reasoning_done":
                    reasoning = ""
                for field in ("server_tool_calls", "annotations", "title", "refusal"):
                    if field in delta:
                        self.metadata[field] = delta[field]
                if (
                    choice.get("finish_reason") is not None
                    and "server_tool_calls" in self.metadata
                ):
                    # Earlier reasoning belongs to the steps in server_tool_calls.
                    self.metadata["reasoning_content"] = reasoning
            if (usage := chunk.get("usage")) and "server_tool_use" in usage:
                self.metadata["server_tool_use"] = usage["server_tool_use"]
            yield line


class DeepseekLargeLanguageModel(OAICompatLargeLanguageModel):
    _THINK_MARKER = "<!--dify-deepseek-reasoning-->"
    _THINK_PATTERN = re.compile(
        rf"<think>\n{re.escape(_THINK_MARKER)}(.*?)\n</think>",
        re.DOTALL | re.IGNORECASE,
    )
    _FLASH_MODELS = (
        "deepseek-flash",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
    )
    _THINKING_MODELS = (*_FLASH_MODELS, "deepseek-v4-pro")
    _THINKING_UNSUPPORTED_PARAMETERS = (
        "temperature",
        "presence_penalty",
        "frequency_penalty",
    )

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        self._add_custom_parameters(credentials)
        apply_dify_headers_if_enabled(credentials)
        credentials["_current_model"] = model
        if user:
            model_parameters["user_id"] = user
        formatted_tools = list(model_parameters.pop("tools", None) or [])
        for name in ("deepseek_web_search", "deepseek_read_url"):
            if model_parameters.pop(name, False):
                formatted_tools.append({"type": name})
        if tools:
            formatted_tools.extend(
                PromptMessageFunction(function=tool).model_dump() for tool in tools
            )
            tools = None
        if formatted_tools:
            if any(
                tool.get("type") in ("deepseek_web_search", "deepseek_read_url")
                for tool in formatted_tools
            ) and model_parameters.get("response_format") not in (None, "text"):
                raise ValueError("DeepSeek web tools require the text response format.")
            model_parameters["tools"] = formatted_tools
        safety_check = model_parameters.get("safety_check")
        if isinstance(safety_check, str):
            model_parameters["safety_check"] = {"level": safety_check}
        if model_parameters.get("safety_check") in (None, {"level": "low"}):
            # Omission is equivalent to low and avoids opting into the extension path.
            model_parameters.pop("safety_check", None)
        title = model_parameters.get("title")
        if isinstance(title, bool):
            model_parameters["title"] = {"enabled": title}
        if model_parameters.get("title") in (None, {"enabled": False}):
            model_parameters.pop("title", None)

        has_client_tools = any(
            tool.get("type") == "function" for tool in formatted_tools
        )
        has_extensions = (
            any(
                tool.get("type") in ("deepseek_web_search", "deepseek_read_url")
                for tool in formatted_tools
            )
            or "safety_check" in model_parameters
            or "title" in model_parameters
        )
        if has_client_tools and has_extensions:
            # DeepSeek rejects client tools + Chatbot extensions in non-thinking mode.
            # Keep the requested tools and safety checks, enabling the required mode.
            model_parameters["thinking"] = True
            if model_parameters.get("reasoning_effort") == "none":
                model_parameters.pop("reasoning_effort")
        self._normalize_model_parameters(model, model_parameters)

        return super()._invoke(
            model,
            credentials,
            self._clean_messages(prompt_messages),
            model_parameters,
            tools,
            stop,
            stream,
        )

    def _clean_messages(self, messages: list[PromptMessage]) -> list[PromptMessage]:
        cleaned: list[PromptMessage] = []
        for original in messages:
            message = original.model_copy(deep=True)

            if isinstance(message, (ToolPromptMessage, SystemPromptMessage)):
                cleaned.append(message)
                continue

            has_tool_calls = isinstance(message, AssistantPromptMessage) and (
                message.tool_calls or self._has_server_tools(message)
            )
            if not message.content and not has_tool_calls:
                continue

            if not cleaned or cleaned[-1].role != message.role:
                cleaned.append(message)
                continue

            previous = cleaned[-1]
            if self._has_server_tools(previous) or self._has_server_tools(message):
                # Step indexes and signatures belong to their original response.
                cleaned.append(message)
                continue
            if isinstance(previous.content, str) and isinstance(message.content, str):
                previous.content = (
                    f"{previous.content}\n\n{message.content}"
                    if previous.content and message.content
                    else previous.content or message.content
                )
            elif isinstance(previous.content, list) and isinstance(
                message.content, list
            ):
                previous.content.extend(message.content)
            elif isinstance(previous.content, str) and isinstance(
                message.content, list
            ):
                previous.content = [
                    TextPromptMessageContent(data=previous.content),
                    *message.content,
                ]
            elif isinstance(previous.content, list) and isinstance(
                message.content, str
            ):
                previous.content.append(TextPromptMessageContent(data=message.content))

            if isinstance(previous, AssistantPromptMessage) and isinstance(
                message, AssistantPromptMessage
            ):
                if isinstance(previous.content, str) and self._THINK_PATTERN.search(
                    previous.content
                ):
                    previous.opaque_body = None
                if message.tool_calls:
                    previous.tool_calls = [
                        *(previous.tool_calls or []),
                        *message.tool_calls,
                    ]

        return cleaned

    @staticmethod
    def _has_server_tools(message: PromptMessage) -> bool:
        return (
            isinstance(message, AssistantPromptMessage)
            and isinstance(message.opaque_body, dict)
            and bool(message.opaque_body.get("server_tool_calls"))
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        apply_dify_headers_if_enabled(credentials)
        super().validate_credentials(model, credentials)

    @classmethod
    def _normalize_model_parameters(cls, model: str, model_parameters: dict) -> None:
        if model not in cls._THINKING_MODELS:
            return

        thinking = model_parameters.get("thinking")
        if thinking is None:
            thinking = model_parameters.get("reasoning_effort", "high") != "none"
        if isinstance(thinking, bool):
            thinking = {"type": "enabled" if thinking else "disabled"}
            model_parameters["thinking"] = thinking

        if not isinstance(thinking, dict):
            return
        if thinking.get("type") == "disabled":
            model_parameters.pop("reasoning_effort", None)
            if model in cls._FLASH_MODELS:
                model_parameters.pop("top_p", None)
            return
        if thinking.get("type") == "enabled":
            for parameter in cls._THINKING_UNSUPPORTED_PARAMETERS:
                model_parameters.pop(parameter, None)
            if model not in cls._FLASH_MODELS:
                model_parameters.pop("top_p", None)

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        credentials["endpoint_url"] = (
            credentials.get("endpoint_url") or ""
        ).strip() or "https://api.deepseek.com"
        credentials["mode"] = LLMMode.CHAT.value
        credentials["function_calling_type"] = "tool_call"
        credentials["stream_function_calling"] = "supported"

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        result = super()._handle_generate_response(
            model,
            credentials,
            response,
            prompt_messages,
        )
        response_message = response.json()["choices"][0].get("message", {})
        metadata = {
            field: response_message[field]
            for field in ("server_tool_calls", "annotations", "title", "refusal")
            if field in response_message
        }
        usage = response.json().get("usage") or {}
        if "server_tool_use" in usage:
            metadata["server_tool_use"] = usage["server_tool_use"]
        if metadata:
            result.message.opaque_body = {
                **(result.message.opaque_body or {}),
                **metadata,
            }
        reasoning_content = response_message.get("reasoning_content")
        if not isinstance(reasoning_content, str):
            return result

        opaque_body = (
            result.message.opaque_body
            if isinstance(result.message.opaque_body, dict)
            else {}
        )
        result.message.opaque_body = {
            **opaque_body,
            "reasoning_content": reasoning_content,
        }
        if reasoning_content:
            result.message.content = (
                f"<think>\n{self._THINK_MARKER}"
                f"{escape(reasoning_content, quote=False)}\n</think>"
                f"{result.message.content or ''}"
            )
        return result

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        observed = _StreamResponse(response)
        for chunk in super()._handle_generate_stream_response(
            model, credentials, observed, prompt_messages
        ):
            if chunk.delta.finish_reason is not None and observed.metadata:
                chunk.delta.message.opaque_body = {
                    **(chunk.delta.message.opaque_body or {}),
                    **observed.metadata,
                }
            yield chunk

    def _wrap_thinking_by_reasoning_content(
        self,
        delta: dict,
        is_reasoning: bool,
    ) -> tuple[str, bool]:
        content = delta.get("content") or ""
        reasoning_content = delta.get("reasoning_content") or delta.get("reasoning")
        if not reasoning_content:
            return ("\n</think>" if is_reasoning else "") + content, False

        output = escape(str(reasoning_content), quote=False)
        if not is_reasoning:
            output = f"<think>\n{self._THINK_MARKER}" + output
        if content or delta.get("tool_calls") or delta.get("function_call"):
            return output + "\n</think>" + content, False
        return output, True

    def _convert_prompt_message_to_dict(
        self,
        message: PromptMessage,
        credentials: dict | None = None,
    ) -> dict:
        credentials = credentials or {}
        message_dict = super()._convert_prompt_message_to_dict(message, credentials)
        if isinstance(message, ToolPromptMessage) and isinstance(message.content, list):
            message_dict["content"] = super()._convert_prompt_message_to_dict(
                UserPromptMessage(content=message.content), credentials
            )["content"]
        if not isinstance(message, AssistantPromptMessage):
            return message_dict

        content = message.content or ""
        reasoning_content = None
        if isinstance(message.opaque_body, dict):
            if "server_tool_calls" in message.opaque_body:
                message_dict["server_tool_calls"] = message.opaque_body[
                    "server_tool_calls"
                ]
            raw_reasoning_content = message.opaque_body.get("reasoning_content")
            if isinstance(raw_reasoning_content, str):
                reasoning_content = raw_reasoning_content

        if isinstance(content, str):
            content, extracted_reasoning = self._extract_reasoning_content(content)
            if reasoning_content is None:
                reasoning_content = extracted_reasoning

        if (
            credentials.get("_current_model", "").lower() in self._THINKING_MODELS
            or reasoning_content is not None
        ):
            message_dict["reasoning_content"] = reasoning_content or ""
            message_dict["content"] = content
        return message_dict

    def _extract_reasoning_content(self, text: str) -> tuple[str, str | None]:
        if not text:
            return text, None

        matches = self._THINK_PATTERN.findall(text)
        reasoning_content = "\n\n".join(map(unescape, matches)) if matches else None
        return self._THINK_PATTERN.sub("", text), reasoning_content
