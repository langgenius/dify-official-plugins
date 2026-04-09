
import re
from collections.abc import Generator
from typing import Optional, Union, cast

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
    ToolPromptMessage,
)




class MoonshotLargeLanguageModel(OAICompatLargeLanguageModel):
    # Pattern to match <think>...</think> blocks (case-insensitive, non-greedy)
    _THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)

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
        self._add_custom_parameters(credentials)
        self._add_function_call(model, credentials)
        user = user[:32] if user else None

        # Store current model for use in _convert_prompt_message_to_dict
        credentials["_current_model"] = model

        # Handle thinking parameter for Kimi K2.5
        if "thinking" in model_parameters:
            thinking = model_parameters.pop("thinking")
            if thinking:
                model_parameters["thinking"] = {"type": "enabled"}
            else:
                model_parameters["thinking"] = {"type": "disabled"}

        # Merge consecutive messages with the same role to strictly follow API specs
        prompt_messages = self._clean_messages(prompt_messages)

        return super()._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user=user)

    def _clean_messages(self, messages: list[PromptMessage]) -> list[PromptMessage]:
        cleaned: list[PromptMessage] = []
        for m in messages:
            # Keep messages that have content or tool calls
            has_tool_calls = isinstance(m, AssistantPromptMessage) and m.tool_calls
            if not m.content and not has_tool_calls:
                continue
            
            # Tool and system messages should NEVER be merged - each has a unique tool_call_id
            if isinstance(m, ToolPromptMessage) or isinstance(m, SystemPromptMessage):
                cleaned.append(m.model_copy())
                continue
            
            if cleaned and cleaned[-1].role == m.role:
                prev = cleaned[-1]
                # Merge content if both are strings
                if isinstance(prev.content, str) and isinstance(m.content, str):
                    if prev.content and m.content:
                        prev.content += "\n\n" + m.content
                    else:
                        prev.content = prev.content or m.content
                
                # Merge tool_calls if both are assistants
                if isinstance(prev, AssistantPromptMessage) and isinstance(m, AssistantPromptMessage):
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

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            model_type=ModelType.LLM,
            features=[ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL, ModelFeature.STREAM_TOOL_CALL]
            if credentials.get("function_calling_type") == "tool_call"
            else [],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 4096)),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens", 4096)),
                    label=I18nObject(en_US="Max Tokens", zh_Hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
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
        if model_schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL}.intersection(
            model_schema.features or []
        ):
            credentials["function_calling_type"] = "tool_call"

    def _convert_prompt_message_to_dict(self, message: PromptMessage, credentials: Optional[dict] = None) -> dict:
        """
        Convert PromptMessage to dict for OpenAI API format.
        For Kimi K2.5 thinking mode, extract <think> content to reasoning_content field.
        """
        credentials = credentials or {}
        model_name = credentials.get("_current_model", "").lower()

        # Check if this is a thinking-enabled model
        is_thinking_model = any(x in model_name for x in ["k2.5", "k2-thinking"])

        # Use base implementation for standard conversion
        message_dict = super()._convert_prompt_message_to_dict(message, credentials)

        if isinstance(message, AssistantPromptMessage):
            content = message.content or ""
            reasoning_content = None

            if isinstance(content, str):
                # Extract <think> content from text
                clean_content, extracted_reasoning = self._extract_reasoning_content(content)
                if extracted_reasoning:
                    reasoning_content = extracted_reasoning
                    content = clean_content

            # For Kimi K2.5 thinking mode, assistant messages MUST include reasoning_content
            # when thinking is enabled (even if empty string) - especially for tool call messages
            if is_thinking_model or reasoning_content is not None:
                message_dict["reasoning_content"] = reasoning_content or ""
                # Update content if it was cleaned
                message_dict["content"] = content

        return message_dict

    def _extract_reasoning_content(self, text: str) -> tuple[str, Optional[str]]:
        if not text:
            return text, None
        
        matches = self._THINK_PATTERN.findall(text)
        reasoning_content = "\n".join(match.strip() for match in matches) if matches else None
        
        # Remove all <think> blocks
        clean_text = self._THINK_PATTERN.sub("", text)
        clean_text = re.sub(r"\n\s*\n", "\n\n", clean_text).strip()
        
        return clean_text, reasoning_content

    def _wrap_thinking_by_reasoning_content(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        If the reasoning response is from delta.get("reasoning_content"), we wrap
        it with HTML think tag.

        :param delta: delta dictionary from LLM streaming response
        :param is_reasoning: is reasoning
        :return: tuple of (processed_content, is_reasoning)
        """

        content = delta.get("content") or ""
        reasoning_content = delta.get("reasoning_content")
        output = content
        if reasoning_content:
            if not is_reasoning:
                output = "<think>\n" + reasoning_content
                is_reasoning = True
            else:
                output = reasoning_content
        else:
            if is_reasoning:
                is_reasoning = False
                if not reasoning_content:
                    output = "\n</think>"
                if content:
                    output += content
            
        return output, is_reasoning
