import logging
from collections.abc import Generator
from dify_plugin.config.logger_format import plugin_logger_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)
from typing import Optional, Union
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
    UserPromptMessage,
)


class SiliconflowLargeLanguageModel(OAICompatLargeLanguageModel):
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
        prompt_messages = self._clean_messages(prompt_messages)
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def _clean_messages(self, messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        Clean messages to merge consecutive identical roles which are strictly forbidden by SiliconFlow.
        Specifically handles:
        1. Consecutive AssistantPromptMessage: merges content and tool_calls.
        2. Consecutive UserPromptMessage: merges string content.
        """
        if not messages:
            return []

        cleaned_messages = [messages[0]]
        
        for msg in messages[1:]:
            last_msg = cleaned_messages[-1]

            # Only merge if both are of the exact same type
            if type(msg) is not type(last_msg):
                cleaned_messages.append(msg)
                continue

            # Try to merge if the new message has the same type as the last one
            if isinstance(msg, AssistantPromptMessage) and isinstance(last_msg, AssistantPromptMessage):
                # Merge Assistant messages: combine content and tool_calls
                parts = [c for c in [last_msg.content, msg.content] if c]
                new_content = "\n".join(parts)
                
                new_tool_calls = (last_msg.tool_calls or []) + (msg.tool_calls or [])
                
                # Update the last message in place
                cleaned_messages[-1] = AssistantPromptMessage(content=new_content, tool_calls=new_tool_calls)

            elif isinstance(msg, UserPromptMessage) and isinstance(last_msg, UserPromptMessage) and \
                 isinstance(last_msg.content, str) and isinstance(msg.content, str):
                # Merge User messages, but only if both contents are simple strings
                new_content = last_msg.content + "\n" + msg.content
                cleaned_messages[-1] = UserPromptMessage(content=new_content)
            else:
                # If types are different, or they are of a type that shouldn't be merged (e.g., System, Tool),
                # or User messages with complex content, just append the new message.
                cleaned_messages.append(msg)

        return cleaned_messages

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

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        credentials["mode"] = "chat"
        if credentials.get("use_international_endpoint", "false") == "true":
            credentials["endpoint_url"] = "https://api.siliconflow.com/v1"
        else:
            credentials["endpoint_url"] = "https://api.siliconflow.cn/v1"
    
    def _add_function_call(self, model: str, credentials: dict) -> None:
        model_schema = self.get_model_schema(model, credentials)
        if model_schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL}.intersection(
            model_schema.features or []
        ):
            credentials["function_calling_type"] = "tool_call"
    
    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            model_type=ModelType.LLM,
            features=(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
                if credentials.get("function_calling_type") == "tool_call"
                else []
            ),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 8000)
                ),
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
                    default=4096,
                    min=1,
                    max=int(credentials.get("max_tokens", 16384)),
                    label=I18nObject(en_US="Max Tokens", zh_Hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_k",
                    use_template="top_k",
                    label=I18nObject(en_US="Top K", zh_Hans="Top K"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="frequency_penalty",
                    use_template="frequency_penalty",
                    label=I18nObject(en_US="Frequency Penalty", zh_Hans="重复惩罚"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="enable_thinking",
                    use_template="enable_thinking",
                    default=True,
                    label=I18nObject(en_US="Thinking mode", zh_Hans="启用思考模式"),
                    type=ParameterType.BOOLEAN,
                ),
                ParameterRule(
                    name="thinking_budget",
                    use_template="thinking_budget",
                    default=512,
                    min=1,
                    max=int(credentials.get("thinking_budget", 8192)),
                    label=I18nObject(en_US="Thinking budget", zh_Hans="思考长度限制"),
                    type=ParameterType.INT,
                ),
            ],
        )
