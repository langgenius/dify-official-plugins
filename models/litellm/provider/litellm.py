from dify_plugin import OAICompatProvider


class LiteLLMProvider(OAICompatProvider):
    """Models are configured one by one, so there are no provider-level credentials."""
