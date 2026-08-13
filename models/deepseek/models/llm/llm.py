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
)
from requests import Response


class DeepseekLargeLanguageModel(OAICompatLargeLanguageModel):
    _THINK_MARKER = "<!--dify-deepseek-reasoning-->"
    _THINK_PATTERN = re.compile(
        rf"<think>\n{re.escape(_THINK_MARKER)}(.*?)\n</think>",
        re.DOTALL | re.IGNORECASE,
    )
    _V4_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
    _THINKING_UNSUPPORTED_PARAMETERS = (
        "temperature",
        "top_p",
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
        credentials["_current_model"] = model
        self._normalize_model_parameters(model, model_parameters)
        if user:
            model_parameters["user_id"] = user
        if tools:
            model_parameters["tools"] = [
                PromptMessageFunction(function=tool).model_dump() for tool in tools
            ]
            tools = None

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

            has_tool_calls = (
                isinstance(message, AssistantPromptMessage) and message.tool_calls
            )
            if not message.content and not has_tool_calls:
                continue

            if not cleaned or cleaned[-1].role != message.role:
                cleaned.append(message)
                continue

            previous = cleaned[-1]
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

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @classmethod
    def _normalize_model_parameters(cls, model: str, model_parameters: dict) -> None:
        if model not in cls._V4_MODELS:
            return

        thinking = model_parameters.get("thinking", True)
        if isinstance(thinking, bool):
            thinking = {"type": "enabled" if thinking else "disabled"}
            model_parameters["thinking"] = thinking

        if not isinstance(thinking, dict):
            return
        if thinking.get("type") == "disabled":
            model_parameters.pop("reasoning_effort", None)
            return
        if thinking.get("type") == "enabled":
            for parameter in cls._THINKING_UNSUPPORTED_PARAMETERS:
                model_parameters.pop(parameter, None)

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
        if not isinstance(message, AssistantPromptMessage):
            return message_dict

        content = message.content or ""
        reasoning_content = None
        if isinstance(message.opaque_body, dict):
            raw_reasoning_content = message.opaque_body.get("reasoning_content")
            if isinstance(raw_reasoning_content, str):
                reasoning_content = raw_reasoning_content

        if isinstance(content, str):
            content, extracted_reasoning = self._extract_reasoning_content(content)
            if reasoning_content is None:
                reasoning_content = extracted_reasoning

        if (
            credentials.get("_current_model", "").lower() in self._V4_MODELS
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
