from collections.abc import Generator
from typing import Optional, Union
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from yarl import URL
from dify_plugin import OAICompatLargeLanguageModel
import re

class DeepseekLargeLanguageModel(OAICompatLargeLanguageModel):
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
        # Merge consecutive messages with the same role to strictly follow API specs
        prompt_messages = self._clean_messages(prompt_messages)
        response = super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )
        return response

    def _clean_messages(self, messages: list[PromptMessage]) -> list[PromptMessage]:
        cleaned: list[PromptMessage] = []
        for m in messages:
            # Tool and system messages should NEVER be filtered or merged
            # - ToolPromptMessage may have empty content (e.g. command succeeded with no output)
            #   but must be kept to match its tool_call_id
            # - SystemPromptMessage should always be preserved as-is
            if isinstance(m, (ToolPromptMessage, SystemPromptMessage)):
                cleaned.append(m.model_copy())
                continue

            # Filter out empty messages (no content and no tool calls)
            has_tool_calls = isinstance(m, AssistantPromptMessage) and m.tool_calls
            if not m.content and not has_tool_calls:
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

    def _log_helper_convert_message(self, prompt_message: PromptMessage) -> dict:
        # Helper method for logging
        message_dict = {"role": "", "content": ""}
        if isinstance(prompt_message, UserPromptMessage):
            message_dict["role"] = "user"
            message_dict["content"] = prompt_message.content
        elif isinstance(prompt_message, AssistantPromptMessage):
            message_dict["role"] = "assistant"
            message_dict["content"] = prompt_message.content or ""
            if prompt_message.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in prompt_message.tool_calls
                ]
        elif isinstance(prompt_message, ToolPromptMessage):
            message_dict["role"] = "tool"
            message_dict["content"] = prompt_message.content
            message_dict["tool_call_id"] = prompt_message.tool_call_id
        elif isinstance(prompt_message, SystemPromptMessage):
             message_dict["role"] = "system"
             message_dict["content"] = prompt_message.content
        return message_dict

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

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @staticmethod
    def _add_custom_parameters(credentials) -> None:
        credentials["endpoint_url"] = str(URL(credentials.get("endpoint_url", "https://api.deepseek.com")))
        credentials["mode"] = LLMMode.CHAT.value
        credentials["function_calling_type"] = "tool_call"
        credentials["stream_function_calling"] = "supported"

    def _convert_prompt_message_to_dict(self, message: PromptMessage, credentials: dict | None = None) -> dict:
        """
        Custom conversion for DeepSeek to handle reasoning_content.
        """
        credentials = credentials or {}
        model_name = credentials.get("_current_model", "").lower()
        
        # Call base logic to get standard role/content/tool_calls
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
            
            # For DeepSeek Reasoner/R1, or if we have extracted reasoning, provide fields.
            # Official doc: assistant messages in history MUST split reasoning_content and content.
            # If reasoning_content is present, it must be a string.
            if "reasoner" in model_name or reasoning_content:
                message_dict["reasoning_content"] = reasoning_content or ""
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