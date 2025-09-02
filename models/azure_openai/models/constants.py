from pydantic import BaseModel

from dify_plugin.entities.model.llm import LLMMode
from dify_plugin.entities.model import (
    PARAMETER_RULE_TEMPLATE,
    AIModelEntity,
    DefaultParameterName,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    PriceConfig,
)

AZURE_OPENAI_API_VERSION = "2024-02-15-preview"

AZURE_DEFAULT_PARAM_SEED_HELP = I18nObject(
    zh_Hans="如果指定，模型将尽最大努力进行确定性采样，使得重复的具有相同种子和参数的请求应该返回相同的结果。不能保证确定性，"
    "您应该参考 system_fingerprint 响应参数来监视变化。",
    en_US="If specified, model will make a best effort to sample deterministically,"
    " such that repeated requests with the same seed and parameters should return the same result."
    " Determinism is not guaranteed, and you should refer to the system_fingerprint response parameter"
    " to monitor changes in the backend.",
)


def _get_max_tokens(default: int, min_val: int, max_val: int) -> ParameterRule:
    rule = ParameterRule(
        name="max_tokens",
        **PARAMETER_RULE_TEMPLATE[DefaultParameterName.MAX_TOKENS],
    )
    rule.default = default
    rule.min = min_val
    rule.max = max_val
    return rule


def _get_o1_max_tokens(default: int, min_val: int, max_val: int) -> ParameterRule:
    rule = ParameterRule(
        name="max_completion_tokens",
        **PARAMETER_RULE_TEMPLATE[DefaultParameterName.MAX_TOKENS],
    )
    rule.default = default
    rule.min = min_val
    rule.max = max_val
    return rule


class AzureBaseModel(BaseModel):
    base_model_name: str
    entity: AIModelEntity


LLM_BASE_MODELS = [
    AzureBaseModel(
        base_model_name="gpt-4o-audio-preview",
        entity=AIModelEntity(
            model="gpt-4o-audio-preview",
            label=I18nObject(
                zh_Hans="gpt-4o-audio-preview",
                en_US="gpt-4o-audio-preview",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.AUDIO,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                ),
                ParameterRule(
                    name="presence_penalty",
                    use_template="presence_penalty",
                ),
                ParameterRule(
                    name="frequency_penalty",
                    use_template="frequency_penalty",
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=4096,
                    min=1,
                    max=16384,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(
                        zh_Hans="回复格式",
                        en_US="Response Format",
                    ),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=2.75,
                output=11.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-35-turbo",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 16385,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.0005,
                output=0.0015,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-35-turbo-16k",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 16385,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16385),
            ],
            pricing=PriceConfig(
                input=0.003,
                output=0.004,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-35-turbo-0125",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 16385,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.0005,
                output=0.0015,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 8192,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=8192),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.03,
                output=0.06,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4-32k",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 32768,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=32768),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.06,
                output=0.12,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4-0125-preview",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.01,
                output=0.03,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4-1106-preview",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.01,
                output=0.03,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16384),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=0.150,
                output=0.600,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-mini-2024-07-18",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16384),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=0.150,
                output=0.600,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16384),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=2.50,
                output=10.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-2024-05-13",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=5.00,
                output=15.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-2024-08-06",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16384),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=2.50,
                output=10.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-2024-11-20",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16384),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=2.50,
                output=10.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4.5-preview",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=16384),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=75.00,
                output=150.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4.1",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 1047576,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=32768),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=2.00,
                output=8.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4.1-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 1047576,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=32768),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=0.40,
                output=1.60,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4.1-nano",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 1047576,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=32768),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=0.10,
                output=0.40,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4-turbo",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.01,
                output=0.03,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4-turbo-2024-04-09",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.01,
                output=0.03,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4-vision-preview",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[ModelFeature.VISION],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=0,
                    min=0,
                    max=2147483647,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object"],
                ),
            ],
            pricing=PriceConfig(
                input=0.01,
                output=0.03,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-35-turbo-instruct",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.COMPLETION.value,
                ModelPropertyKey.CONTEXT_SIZE: 4096,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
            ],
            pricing=PriceConfig(
                input=0.0015,
                output=0.002,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="text-davinci-003",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.COMPLETION.value,
                ModelPropertyKey.CONTEXT_SIZE: 4096,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="presence_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.PRESENCE_PENALTY],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_max_tokens(default=512, min_val=1, max_val=4096),
            ],
            pricing=PriceConfig(
                input=0.02,
                output=0.02,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="o1-preview",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                _get_o1_max_tokens(default=512, min_val=1, max_val=32768),
            ],
            pricing=PriceConfig(
                input=15.00,
                output=60.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="o1-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                _get_o1_max_tokens(default=512, min_val=1, max_val=65536),
            ],
            pricing=PriceConfig(
                input=1.10,
                output=4.40,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="o1",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.VISION,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 200000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                ),
                _get_o1_max_tokens(default=512, min_val=1, max_val=100000),
            ],
            pricing=PriceConfig(
                input=15.00,
                output=60.00,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="o3-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 200000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                ),
                _get_o1_max_tokens(default=512, min_val=1, max_val=100000),
            ],
            pricing=PriceConfig(
                input=1.10,
                output=4.40,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="o4-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.VISION,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 200000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                ),
                _get_o1_max_tokens(default=512, min_val=1, max_val=100000),
            ],
            pricing=PriceConfig(
                input=1.10,
                output=4.40,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="o3",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.VISION,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 200000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                ),
                _get_o1_max_tokens(default=512, min_val=1, max_val=100000),
            ],
            pricing=PriceConfig(
                input=2,
                output=8,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-5",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.VISION,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 272000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["minimal", "low", "medium", "high"],
                ),
                ParameterRule(
                    name="verbosity",
                    label=I18nObject(zh_Hans="详细程度", en_US="verbosity"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="约束模型响应的详细程度。较低的值将产生更简洁的响应，而较高的值将产生更详细的响应。"
                                "支持的值包括low、medium和high",
                        en_US="Constrains the verbosity of the model's response. "
                              "Lower values will result in more concise responses, "
                              "while higher values will result in more verbose responses. "
                              "Currently supported values are low, medium, and high",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                    default="medium",
                ),
                _get_o1_max_tokens(default=4096, min_val=1, max_val=128000),
            ],
            pricing=PriceConfig(
                input=1.25,
                output=10,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-5-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.VISION,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 272000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["minimal", "low", "medium", "high"],
                ),
                ParameterRule(
                    name="verbosity",
                    label=I18nObject(zh_Hans="详细程度", en_US="verbosity"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="约束模型响应的详细程度。较低的值将产生更简洁的响应，而较高的值将产生更详细的响应。"
                                "支持的值包括low、medium和high",
                        en_US="Constrains the verbosity of the model's response. "
                              "Lower values will result in more concise responses, "
                              "while higher values will result in more verbose responses. "
                              "Currently supported values are low, medium, and high",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                    default="medium",
                ),
                _get_o1_max_tokens(default=4096, min_val=1, max_val=128000),
            ],
            pricing=PriceConfig(
                input=0.25,
                output=2,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-5-nano",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.VISION,
                ModelFeature.STRUCTURED_OUTPUT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 272000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["minimal", "low", "medium", "high"],
                ),
                ParameterRule(
                    name="verbosity",
                    label=I18nObject(zh_Hans="详细程度", en_US="verbosity"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="约束模型响应的详细程度。较低的值将产生更简洁的响应，而较高的值将产生更详细的响应。"
                                "支持的值包括low、medium和high",
                        en_US="Constrains the verbosity of the model's response. "
                              "Lower values will result in more concise responses, "
                              "while higher values will result in more verbose responses. "
                              "Currently supported values are low, medium, and high",
                    ),
                    required=False,
                    options=["low", "medium", "high"],
                    default="medium",
                ),
                _get_o1_max_tokens(default=4096, min_val=1, max_val=128000),
            ],
            pricing=PriceConfig(
                input=0.05,
                output=0.4,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-5-chat",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 128000,
            },
            parameter_rules=[
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["minimal", "low", "medium", "high"],
                ),
                _get_o1_max_tokens(default=4096, min_val=1, max_val=16384),
            ],
            pricing=PriceConfig(
                input=1.25,
                output=10,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="grok-3",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 131072,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_o1_max_tokens(default=512, min_val=1, max_val=32768),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=2,
                    min=0,
                    max=1,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
            ],
            pricing=PriceConfig(
                input=3,
                output=15,
                unit=0.000001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="grok-3-mini",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(
                en_US="fake-deployment-name-label",
            ),
            model_type=ModelType.LLM,
            features=[
                ModelFeature.AGENT_THOUGHT,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
            ],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
                ModelPropertyKey.CONTEXT_SIZE: 131072,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TEMPERATURE],
                ),
                ParameterRule(
                    name="top_p",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.TOP_P],
                ),
                ParameterRule(
                    name="frequency_penalty",
                    **PARAMETER_RULE_TEMPLATE[DefaultParameterName.FREQUENCY_PENALTY],
                ),
                _get_o1_max_tokens(default=512, min_val=1, max_val=32768),
                ParameterRule(
                    name="seed",
                    label=I18nObject(zh_Hans="种子", en_US="Seed"),
                    type="int",
                    help=AZURE_DEFAULT_PARAM_SEED_HELP,
                    required=False,
                    precision=2,
                    min=0,
                    max=1,
                ),
                ParameterRule(
                    name="response_format",
                    label=I18nObject(zh_Hans="回复格式", en_US="response_format"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="指定模型必须输出的格式",
                        en_US="specifying the format that the model must output",
                    ),
                    required=False,
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    label=I18nObject(en_US="JSON Schema"),
                    type="text",
                    help=I18nObject(
                        zh_Hans="设置返回的json schema，llm将按照它返回",
                        en_US="Set a response json schema will ensure LLM to adhere it.",
                    ),
                    required=False,
                ),
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(zh_Hans="推理工作", en_US="reasoning_effort"),
                    type="string",
                    help=I18nObject(
                        zh_Hans="限制推理模型的推理工作",
                        en_US="constrains effort on reasoning for reasoning models",
                    ),
                    required=False,
                    options=["medium", "high"],
                ),
            ],
            pricing=PriceConfig(
                input=0.3,
                output=0.5,
                unit=0.000001,
                currency="USD",
            ),
        ),
    )
]
EMBEDDING_BASE_MODELS = [
    AzureBaseModel(
        base_model_name="text-embedding-ada-002",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TEXT_EMBEDDING,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: 8097,
                ModelPropertyKey.MAX_CHUNKS: 32,
            },
            pricing=PriceConfig(
                input=0.0001,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="text-embedding-3-small",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TEXT_EMBEDDING,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: 8191,
                ModelPropertyKey.MAX_CHUNKS: 32,
            },
            pricing=PriceConfig(
                input=0.00002,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="text-embedding-3-large",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TEXT_EMBEDDING,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: 8191,
                ModelPropertyKey.MAX_CHUNKS: 32,
            },
            pricing=PriceConfig(
                input=0.00013,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
]
SPEECH2TEXT_BASE_MODELS = [
    AzureBaseModel(
        base_model_name="whisper-1",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={
                ModelPropertyKey.FILE_UPLOAD_LIMIT: 25,
                ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS: "flac,mp3,mp4,mpeg,mpga,m4a,ogg,wav,webm",
            },
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-transcribe",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={
                ModelPropertyKey.FILE_UPLOAD_LIMIT: 25,
                ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS: "flac,mp3,mp4,mpeg,mpga,m4a,ogg,wav,webm",
            },
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-mini-transcribe",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={
                ModelPropertyKey.FILE_UPLOAD_LIMIT: 25,
                ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS: "flac,mp3,mp4,mpeg,mpga,m4a,ogg,wav,webm",
            },
        ),
    ),
]
TTS_BASE_MODELS = [
    AzureBaseModel(
        base_model_name="tts-1",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TTS,
            model_properties={
                ModelPropertyKey.DEFAULT_VOICE: "alloy",
                ModelPropertyKey.VOICES: [
                    {
                        "mode": "alloy",
                        "name": "Alloy",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "echo",
                        "name": "Echo",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "fable",
                        "name": "Fable",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "onyx",
                        "name": "Onyx",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "nova",
                        "name": "Nova",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "shimmer",
                        "name": "Shimmer",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                ],
                ModelPropertyKey.WORD_LIMIT: 120,
                ModelPropertyKey.AUDIO_TYPE: "mp3",
                ModelPropertyKey.MAX_WORKERS: 5,
            },
            pricing=PriceConfig(
                input=0.015,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="tts-1-hd",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TTS,
            model_properties={
                ModelPropertyKey.DEFAULT_VOICE: "alloy",
                ModelPropertyKey.VOICES: [
                    {
                        "mode": "alloy",
                        "name": "Alloy",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "echo",
                        "name": "Echo",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "fable",
                        "name": "Fable",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "onyx",
                        "name": "Onyx",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "nova",
                        "name": "Nova",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "shimmer",
                        "name": "Shimmer",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                ],
                ModelPropertyKey.WORD_LIMIT: 120,
                ModelPropertyKey.AUDIO_TYPE: "mp3",
                ModelPropertyKey.MAX_WORKERS: 5,
            },
            pricing=PriceConfig(
                input=0.03,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
    AzureBaseModel(
        base_model_name="gpt-4o-mini-tts",
        entity=AIModelEntity(
            model="fake-deployment-name",
            label=I18nObject(en_US="fake-deployment-name-label"),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TTS,
            model_properties={
                ModelPropertyKey.DEFAULT_VOICE: "alloy",
                ModelPropertyKey.VOICES: [
                    {
                        "mode": "alloy",
                        "name": "Alloy",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "ash",
                        "name": "Ash",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "ballad",
                        "name": "Ballad",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "coral",
                        "name": "Coral",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "echo",
                        "name": "Echo",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "fable",
                        "name": "Fable",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "nova",
                        "name": "Nova",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "onyx",
                        "name": "Onyx",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "sage",
                        "name": "Sage",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "shimmer",
                        "name": "Shimmer",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                    {
                        "mode": "verse",
                        "name": "Verse",
                        "language": [
                            "zh-Hans",
                            "en-US",
                            "de-DE",
                            "fr-FR",
                            "es-ES",
                            "it-IT",
                            "th-TH",
                            "id-ID",
                            "ja-JP",
                        ],
                    },
                ],
                ModelPropertyKey.WORD_LIMIT: 120,
                ModelPropertyKey.AUDIO_TYPE: "mp3",
                ModelPropertyKey.MAX_WORKERS: 5,
            },
            pricing=PriceConfig(
                input=0.0006,
                output=0.012,
                unit=0.001,
                currency="USD",
            ),
        ),
    ),
]
