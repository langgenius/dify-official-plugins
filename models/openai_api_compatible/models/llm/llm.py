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
)
from dify_plugin.interfaces.model.openai_compatible.llm import (
    OAICompatLargeLanguageModel,
)


class OpenAILargeLanguageModel(OAICompatLargeLanguageModel):
    def get_customizable_model_schema(
        self, model: str, credentials: Mapping
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

            entity.parameter_rules.append(ParameterRule(
                name=DefaultParameterName.RESPONSE_FORMAT.value,
                label=I18nObject(en_US="Response Format", zh_Hans="回复格式"),
                help=I18nObject(
                    en_US="Specifying the format that the model must output.",
                    zh_Hans="指定模型必须输出的格式。",
                ),
                type=ParameterType.STRING,
                options=["text", "json_object", "json_schema"],
                required=False,
            ))
            entity.parameter_rules.append(ParameterRule(
                name=DefaultParameterName.JSON_SCHEMA.value,
                use_template=DefaultParameterName.JSON_SCHEMA.value
            ))

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
        # 1. Forcing the response format to 'json_object'.
        # 2. Injecting the JSON schema directly into the system prompt to guide the model.
        # This ensures models like gpt-4o produce the correct structured output.
        # The original 'json_schema' parameter is intentionally not removed to support
        # other potential OpenAI-compatible models that might handle it differently.
        if model_parameters.get("response_format") == "json_schema":
            model_parameters["response_format"] = "json_object"
            json_schema_str = model_parameters.get("json_schema")  # Use .get() instead of .pop() for safety

            if json_schema_str:
                structured_output_prompt = (
                    "Your response must be a JSON object that validates against the following JSON schema, and nothing else.\n"
                    f"JSON Schema: ```json\n{json_schema_str}\n```"
                )

                existing_system_prompt = next((p for p in prompt_messages if p.role == PromptMessageRole.SYSTEM), None)
                if existing_system_prompt:
                    existing_system_prompt.content = structured_output_prompt + "\n\n" + existing_system_prompt.content
                else:
                    prompt_messages.insert(0, SystemPromptMessage(content=structured_output_prompt))

        enable_thinking = model_parameters.pop("enable_thinking", None)
        if enable_thinking is not None:
            model_parameters["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}

        return super()._invoke(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )
