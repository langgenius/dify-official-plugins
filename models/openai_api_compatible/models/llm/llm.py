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

        agent_though_support = credentials.get("agent_though_support", "not_supported")
        if agent_though_support == "supported":
            try:
                entity.features.index(ModelFeature.AGENT_THOUGHT)
            except ValueError:
                entity.features.append(ModelFeature.AGENT_THOUGHT)

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
                        zh_Hans="指定模型必须输出的格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["text", "json_object", "json_schema"],
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

        entity.parameter_rules += [
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
        ]
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

        enable_thinking = model_parameters.pop("enable_thinking", None)
        if enable_thinking is not None:
            model_parameters["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}

        # Remove thinking content from assistant messages for better performance.
        with suppress(Exception):
            self._drop_analyze_channel(prompt_messages)

        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )
