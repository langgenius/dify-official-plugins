from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    ModelFeature,
    ParameterRule,
    ParameterType,
)

INLINE_FILE_PARAMETER_NAME = "use_inline_file"

_FILE_INPUT_FEATURES = {
    ModelFeature.VISION.value,
    ModelFeature.DOCUMENT.value,
    ModelFeature.VIDEO.value,
    ModelFeature.AUDIO.value,
}


def model_accepts_file_inputs(model_schema: AIModelEntity) -> bool:
    features = {
        getattr(feature, "value", feature) for feature in model_schema.features or []
    }
    return bool(features & _FILE_INPUT_FEATURES)


def inline_file_parameter_rule() -> ParameterRule:
    return ParameterRule(
        name=INLINE_FILE_PARAMETER_NAME,
        type=ParameterType.BOOLEAN,
        required=True,
        default=False,
        label=I18nObject(
            en_us="Use inline file mode",
            zh_hans="使用内嵌文件模式",
        ),
        help=I18nObject(
            en_us=(
                "When enabled, files are embedded directly in the request. "
                "When disabled, files are uploaded with the Gemini Files API."
            ),
            zh_hans="启用后直接内嵌文件；禁用后使用 Gemini Files API 上传文件。",
        ),
    )


def with_inline_file_parameter(model_schema: AIModelEntity) -> AIModelEntity:
    schema = model_schema.model_copy(deep=True)
    rules = list(schema.parameter_rules or [])

    if not model_accepts_file_inputs(schema) or any(
        rule.name == INLINE_FILE_PARAMETER_NAME for rule in rules
    ):
        schema.parameter_rules = rules
        return schema

    insert_at = next(
        (
            index
            for index, rule in enumerate(rules)
            if rule.name in {"json_schema", "response_format"}
        ),
        len(rules),
    )
    rules.insert(insert_at, inline_file_parameter_rule())
    schema.parameter_rules = rules
    return schema
