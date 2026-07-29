from decimal import Decimal
from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
    PriceConfig,
)
from dify_plugin.entities.model.llm import LLMMode
from dify_plugin import OAICompatLargeLanguageModel


class VesslAILargeLanguageModel(OAICompatLargeLanguageModel):
    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        features = []
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            model_type=ModelType.LLM,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            features=features,
            model_properties={ModelPropertyKey.MODE: credentials.get("mode")},
            parameter_rules=[
                ParameterRule(
                    name=DefaultParameterName.TEMPERATURE.value,
                    label=I18nObject(en_us="Temperature"),
                    type=ParameterType.FLOAT,
                    default=float(credentials.get("temperature", 0.7)),
                    min=0,
                    max=2,
                    precision=2,
                ),
                ParameterRule(
                    name=DefaultParameterName.TOP_P.value,
                    label=I18nObject(en_us="Top P"),
                    type=ParameterType.FLOAT,
                    default=float(credentials.get("top_p", 1)),
                    min=0,
                    max=1,
                    precision=2,
                ),
                ParameterRule(
                    name=DefaultParameterName.TOP_K.value,
                    label=I18nObject(en_us="Top K"),
                    type=ParameterType.INT,
                    default=int(credentials.get("top_k", 50)),
                    min=-2147483647,
                    max=2147483647,
                    precision=0,
                ),
                ParameterRule(
                    name=DefaultParameterName.MAX_TOKENS.value,
                    label=I18nObject(en_us="Max Tokens"),
                    type=ParameterType.INT,
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens_to_sample", 4096)),
                ),
            ],
            pricing=PriceConfig(
                input=Decimal(credentials.get("input_price", 0)),
                output=Decimal(credentials.get("output_price", 0)),
                unit=Decimal(credentials.get("unit", 0)),
                currency=credentials.get("currency", "USD"),
            ),
        )
        if credentials["mode"] == "chat":
            entity.model_properties[ModelPropertyKey.MODE] = LLMMode.CHAT.value
        elif credentials["mode"] == "completion":
            entity.model_properties[ModelPropertyKey.MODE] = LLMMode.COMPLETION.value
        else:
            raise ValueError(f"Unknown completion type {credentials['completion_type']}")
        return entity
