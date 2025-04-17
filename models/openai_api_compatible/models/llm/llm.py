from typing import Mapping

from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    I18nObject,
    ModelFeature,
    ParameterRule,
    ParameterType
)

from dify_plugin.interfaces.model.openai_compatible.llm import (
    OAICompatLargeLanguageModel,
)


class OpenAILargeLanguageModel(OAICompatLargeLanguageModel):
    def get_customizable_model_schema(self, model: str, credentials: Mapping) -> AIModelEntity:
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
            entity.label= I18nObject(
                en_US=credentials["display_name"],
                zh_Hans=credentials["display_name"]
            )

        return entity
