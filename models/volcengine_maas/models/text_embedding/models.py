from pydantic import BaseModel
from dify_plugin.entities.model import ModelFeature


class ModelProperties(BaseModel):
    context_size: int
    max_chunks: int


class ModelConfig(BaseModel):
    properties: ModelProperties
    features: list[ModelFeature]


ModelConfigs = {
    "Doubao-embedding": ModelConfig(
        properties=ModelProperties(context_size=4096, max_chunks=32), features=[]
    ),
    "Doubao-embedding-large": ModelConfig(
        properties=ModelProperties(context_size=4096, max_chunks=32), features=[]
    ),
    "Doubao-embedding-vision": ModelConfig(
        properties=ModelProperties(context_size=128000, max_chunks=32),
        features=[ModelFeature.VISION],
    ),
}


def get_model_config(credentials: dict) -> ModelConfig:
    base_model = credentials.get("base_model_name", "")
    model_configs = ModelConfigs.get(base_model)
    if not model_configs:
        return ModelConfig(
            properties=ModelProperties(
                context_size=int(credentials.get("context_size", 4096)),
                max_chunks=int(credentials.get("max_chunks", 1)),
            ),
            features=[],
        )
    return model_configs
