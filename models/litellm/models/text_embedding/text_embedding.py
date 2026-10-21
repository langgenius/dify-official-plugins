from dify_plugin import OAICompatEmbeddingModel
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey


class LiteLLMTextEmbeddingModel(OAICompatEmbeddingModel):
    """Embedding models served by a LiteLLM Proxy."""

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)
        # The base class fixes the batch size at 1. Use the value from the model form.
        max_chunks = int(credentials.get("max_chunks") or 1)
        entity.model_properties[ModelPropertyKey.MAX_CHUNKS] = max(max_chunks, 1)
        return entity
