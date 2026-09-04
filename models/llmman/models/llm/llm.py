# Import the module, not the class, so the SDK loader sees one LargeLanguageModel subclass here.
from dify_plugin.interfaces.model.openai_compatible import llm as _oai


class LlmmanLargeLanguageModel(_oai.OAICompatLargeLanguageModel):
    """llmman (https://github.com/llmmanorg/llmman) chat/completion models via /v1."""
