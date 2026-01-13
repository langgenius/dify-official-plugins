import re
from contextlib import suppress
from typing import Mapping, Optional, Union, Generator

from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    I18nObject,
    ModelFeature,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
    AssistantPromptMessage,
)
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel
from typing import List


class OpenAILargeLanguageModel(OAICompatLargeLanguageModel):
    # Pre-compiled regex for better performance
    _THINK_PATTERN = re.compile(r"^<think>.*?</think>\s*", re.DOTALL)

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)

        structured_output_support = credentials.get("structured_output_support", "not_supported")
        if structured_output_support == "supported":
            # ----
            # The following section should be added after the new version of `dify-plugin-sdks`
            # is released.
            # Related Commit:
            # https://github.com/langgenius/dify-plugin-sdks/commit/0690573a879caf43f92494bf411f45a1835d96f6
            # ----
            # try:
            #     entity.features.index(ModelFeature.STRUCTURED_OUTPUT)
            # except ValueError:
            #     entity.features.append(ModelFeature.STRUCTURED_OUTPUT)

            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.RESPONSE_FORMAT.value,
                    label=I18nObject(en_US="Response Format", zh_Hans="回复格式"),
                    help=I18nObject(
                        en_US="Specifying the format that the model must output.",
                        zh_Hans="指定模型必须输出的回复格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["text", "json_object", "json_schema"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="reasoning_format",
                    label=I18nObject(en_US="Reasoning Format", zh_Hans="推理格式"),
                    help=I18nObject(
                        en_US="Specifying the format that the model must output reasoning.",
                        zh_Hans="指定模型必须输出的推理格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["none", "auto", "deepseek", "deepseek-legacy"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.JSON_SCHEMA.value,
                    use_template=DefaultParameterName.JSON_SCHEMA.value,
                )
            )

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_US=credentials["display_name"], zh_Hans=credentials["display_name"]
            )

        entity.parameter_rules.append(
            ParameterRule(
                name="strict_compatibility",
                label=I18nObject(en_US="Strict compatibility mode", zh_Hans="严格兼容模式"),
                help=I18nObject(
                    en_US=(
                        "Whether to prioritize strict OpenAI compatibility. "
                        "When True, OpenAI compatibility is prioritized and extended parameters "
                        "(e.g., thinking, chat_template_kwargs) are not added. "
                        "Set to False to enable these extensions."
                    ),
                    zh_Hans=(
                        "是否优先严格的 OpenAI 兼容性。"
                        "为 True 时，将优先 OpenAI 兼容性，并且不会添加扩展参数（例如 thinking、chat_template_kwargs）。"
                        "设为 False 以启用这些扩展。"
                    )
                ),
                type=ParameterType.BOOLEAN,
                required=False,
            )
        )

        # Configure thinking mode parameter based on model support
        agent_thought_support = credentials.get("agent_thought_support", "not_supported")
        
        # Add AGENT_THOUGHT feature if thinking mode is supported (either mode)
        if agent_thought_support in ["supported", "only_thinking_supported"] and ModelFeature.AGENT_THOUGHT not in entity.features:
            entity.features.append(ModelFeature.AGENT_THOUGHT)
        
        # Only add the enable_thinking parameter if the model supports both modes
        # If only_thinking_supported, the parameter is not needed (forced behavior)
        if agent_thought_support == "supported":
            entity.parameter_rules.append(
                ParameterRule(
                    name="enable_thinking",
                    label=I18nObject(en_US="Thinking mode", zh_Hans="思考模式"),
                    help=I18nObject(
                        en_US="Whether to enable thinking mode, applicable to various thinking mode models deployed on reasoning frameworks such as vLLM and SGLang, for example Qwen3.",
                        zh_Hans="是否开启思考模式，适用于vLLM和SGLang等推理框架部署的多种思考模式模型，例如Qwen3。",
                    ),
                    type=ParameterType.BOOLEAN,
                    required=False,
                )
            )

        if agent_thought_support in ["supported", "only_thinking_supported"]:
            entity.parameter_rules.append(
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(en_US="Reasoning effort", zh_Hans="推理工作"),
                    help=I18nObject(
                        en_US="Constrains effort on reasoning for reasoning models.",
                        zh_Hans="限制推理模型的推理工作。",
                    ),
                    type=ParameterType.STRING,
                    options=["low", "medium", "high"],
                    required=False,
                )
            )
        
        return entity

    @classmethod
    def _drop_analyze_channel(cls, prompt_messages: List[PromptMessage]) -> None:
        """
        Remove thinking content from assistant messages for better performance.

        Uses early exit and pre-compiled regex to minimize overhead.
        Args:
            prompt_messages:

        Returns:

        """
        for p in prompt_messages:
            # Early exit conditions
            if not isinstance(p, AssistantPromptMessage):
                continue
            if not isinstance(p.content, str):
                continue
            # Quick check to avoid regex if not needed
            if not p.content.startswith("<think>"):
                continue

            # Only perform regex substitution when necessary
            new_content = cls._THINK_PATTERN.sub("", p.content, count=1)
            # Only update if changed
            if new_content != p.content:
                p.content = new_content

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
        # Compatibility adapter for Dify's 'json_schema' structured output mode.
        # The base class does not natively handle the 'json_schema' parameter. This block
        # translates it into a standard OpenAI-compatible request by:
        # 1. Injecting the JSON schema directly into the system prompt to guide the model.
        # This ensures models like gpt-4o produce the correct structured output.
        if model_parameters.get("response_format") == "json_schema":
            # Use .get() instead of .pop() for safety
            json_schema_str = model_parameters.get("json_schema")

            if json_schema_str:
                structured_output_prompt = (
                    "Your response must be a JSON object that validates against the following JSON schema, and nothing else.\n"
                    f"JSON Schema: ```json\n{json_schema_str}\n```"
                )

                existing_system_prompt = next(
                    (p for p in prompt_messages if p.role == PromptMessageRole.SYSTEM), None
                )
                if existing_system_prompt:
                    existing_system_prompt.content = (
                        structured_output_prompt + "\n\n" + existing_system_prompt.content
                    )
                else:
                    prompt_messages.insert(0, SystemPromptMessage(content=structured_output_prompt))

        # Handle thinking mode based on model support configuration
        agent_thought_support = credentials.get("agent_thought_support", "not_supported")
        enable_thinking_value = None
        if agent_thought_support == "only_thinking_supported":
            # Force enable thinking mode
            enable_thinking_value = True
        elif agent_thought_support == "not_supported":
            # Force disable thinking mode
            enable_thinking_value = False
        else:
            # Both modes supported - use user's preference
            user_enable_thinking = model_parameters.pop("enable_thinking", None)
            if user_enable_thinking is not None:
                enable_thinking_value = bool(user_enable_thinking)

        user_strict_compatibility = model_parameters.pop("strict_compatibility", None)
        # Default `strict_compatibility_value` is False.
        strict_compatibility_value = False
        if user_strict_compatibility is not None:
            strict_compatibility_value = bool(user_strict_compatibility)

        if enable_thinking_value is not None and strict_compatibility_value is False:
            # Only apply when `strict_compatibility_value` is False since
            # `chat_template_kwargs` and `thinking` are non-standard parameters.

            chat_template_kwargs = model_parameters.setdefault("chat_template_kwargs", {})
            # Support vLLM/SGLang format (chat_template_kwargs)
            chat_template_kwargs["enable_thinking"] = enable_thinking_value
            chat_template_kwargs["thinking"] = enable_thinking_value

            # Support Zhipu AI API format (top-level thinking parameter)
            # This allows compatibility with Zhipu's official API format: {"thinking": {"type": "enabled/disabled"}}
            model_parameters["thinking"] = {
                "type": "enabled" if enable_thinking_value else "disabled"
            }

        reasoning_effort_value = model_parameters.pop("reasoning_effort", None)
        if enable_thinking_value is True and reasoning_effort_value is not None:
            # Propagate reasoning_effort to both:
            # - top-level OpenAI Chat Completions param, and
            # - chat_template_kwargs for runtimes that read template kwargs (e.g., llama.cpp).
            # Only apply when thinking mode is explicitly enabled.
            model_parameters["reasoning_effort"] = reasoning_effort_value
            if strict_compatibility_value is False:
                # Only apply when `strict_compatibility_value` is False since
                # `chat_template_kwargs` is a non-standard parameter.
                chat_template_kwargs = model_parameters.setdefault("chat_template_kwargs", {})
                chat_template_kwargs["reasoning_effort"] = reasoning_effort_value
        
        # Remove thinking content from assistant messages for better performance.
        with suppress(Exception):
            self._drop_analyze_channel(prompt_messages)

        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )
