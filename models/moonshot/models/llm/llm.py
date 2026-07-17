import re
from collections.abc import Generator

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from requests import Response


class MoonshotLargeLanguageModel(OAICompatLargeLanguageModel):
    _THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
    _THINKING_MODELS = {
        "kimi-k2-thinking",
        "kimi-k2-thinking-turbo",
        "kimi-k2.5",
        "kimi-k2.6",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
        "kimi-k3",
    }

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
        self._add_function_call(model, credentials)
        user = user[:32] if user else None

        credentials["_current_model"] = model

        if "thinking" in model_parameters:
            thinking = model_parameters.pop("thinking")
            if thinking:
                model_parameters["thinking"] = {"type": "enabled"}
            else:
                model_parameters["thinking"] = {"type": "disabled"}

        prompt_messages = self._clean_messages(prompt_messages)

        return super()._invoke(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user=user,
        )

    def _clean_messages(self, messages: list[PromptMessage]) -> list[PromptMessage]:
        cleaned: list[PromptMessage] = []
        for m in messages:
            has_tool_calls = isinstance(m, AssistantPromptMessage) and m.tool_calls
            if not m.content and not has_tool_calls:
                continue

            if isinstance(m, ToolPromptMessage) or isinstance(m, SystemPromptMessage):
                cleaned.append(m.model_copy())
                continue

            if cleaned and cleaned[-1].role == m.role:
                prev = cleaned[-1]
                if isinstance(prev.content, str) and isinstance(m.content, str):
                    if prev.content and m.content:
                        prev.content += "\n\n" + m.content
                    else:
                        prev.content = prev.content or m.content
                elif isinstance(prev.content, list) and isinstance(m.content, list):
                    prev.content = [*prev.content, *m.content]
                elif isinstance(prev.content, str) and isinstance(m.content, list):
                    prev.content = [
                        TextPromptMessageContent(data=prev.content),
                        *m.content,
                    ]
                elif isinstance(prev.content, list) and isinstance(m.content, str):
                    prev.content = [
                        *prev.content,
                        TextPromptMessageContent(data=m.content),
                    ]

                if isinstance(prev, AssistantPromptMessage) and isinstance(
                    m, AssistantPromptMessage
                ):
                    if isinstance(prev.content, str) and self._THINK_PATTERN.search(
                        prev.content
                    ):
                        prev.opaque_body = None
                    if m.tool_calls:
                        if not prev.tool_calls:
                            prev.tool_calls = []
                        prev.tool_calls.extend(m.tool_calls)
            else:
                cleaned.append(m.model_copy())
        return cleaned

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity | None:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.TOOL_CALL,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ]
            if credentials.get("function_calling_type") == "tool_call"
            else [],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 4096)
                ),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_us="Temperature", zh_hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens", 4096)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
            ],
        )

    def _add_custom_parameters(self, credentials: dict) -> None:
        credentials["mode"] = "chat"
        if "endpoint_url" not in credentials or credentials["endpoint_url"] == "":
            credentials["endpoint_url"] = "https://api.moonshot.cn/v1"

    def _add_function_call(self, model: str, credentials: dict) -> None:
        model_schema = self.get_model_schema(model, credentials)
        if model_schema and {
            ModelFeature.TOOL_CALL,
            ModelFeature.MULTI_TOOL_CALL,
        }.intersection(model_schema.features or []):
            credentials["function_calling_type"] = "tool_call"

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
        if LLMMode.value_of(credentials["mode"]) is not LLMMode.CHAT:
            return result

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
                f"<think>{reasoning_content}</think>{result.message.content or ''}"
            )
        return result

    def _convert_prompt_message_to_dict(
        self,
        message: PromptMessage,
        credentials: dict | None = None,
    ) -> dict:
        credentials = credentials or {}
        model_name = credentials.get("_current_model", "").lower()
        is_thinking_model = model_name in self._THINKING_MODELS
        message_dict = super()._convert_prompt_message_to_dict(message, credentials)

        if isinstance(message, UserPromptMessage) and isinstance(message.content, list):
            for index, content in enumerate(message.content):
                if isinstance(content, VideoPromptMessageContent):
                    message_dict["content"].insert(
                        index,
                        {
                            "type": "video_url",
                            "video_url": {"url": content.data},
                        },
                    )

        if isinstance(message, AssistantPromptMessage):
            content = message.content or ""
            reasoning_content = None

            if isinstance(message.opaque_body, dict):
                raw_reasoning_content = message.opaque_body.get("reasoning_content")
                if isinstance(raw_reasoning_content, str):
                    reasoning_content = raw_reasoning_content

            if isinstance(content, str):
                clean_content, extracted_reasoning = self._extract_reasoning_content(
                    content
                )
                if reasoning_content is None and extracted_reasoning is not None:
                    reasoning_content = extracted_reasoning
                if extracted_reasoning is not None:
                    content = clean_content

            if is_thinking_model or reasoning_content is not None:
                message_dict["reasoning_content"] = reasoning_content or ""
                message_dict["content"] = content

        return message_dict

    def _extract_reasoning_content(self, text: str) -> tuple[str, str | None]:
        if not text:
            return text, None

        matches = self._THINK_PATTERN.findall(text)
        reasoning_content = "\n\n".join(matches) if matches else None
        return self._THINK_PATTERN.sub("", text), reasoning_content

    def _wrap_thinking_by_reasoning_content(
        self,
        delta: dict,
        is_reasoning: bool,
    ) -> tuple[str, bool]:
        content = delta.get("content") or ""
        reasoning_content = delta.get("reasoning_content")
        if reasoning_content == "":
            if content and is_reasoning:
                return "</think>" + content, False
            return content, is_reasoning

        if reasoning_content is not None:
            output = reasoning_content
            if not is_reasoning:
                output = "<think>" + output
                is_reasoning = True

            if content:
                output += "</think>" + content
                is_reasoning = False
            return output, is_reasoning

        if is_reasoning:
            return "</think>" + content, False
        return content, False
