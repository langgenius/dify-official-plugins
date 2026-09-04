# Import the module, not the class, so the SDK loader sees one TextEmbeddingModel subclass here.
from dify_plugin.interfaces.model.openai_compatible import text_embedding as _oai


class LlmmanTextEmbeddingModel(_oai.OAICompatEmbeddingModel):
    """llmman (https://github.com/llmmanorg/llmman) embeddings via /v1/embeddings."""
