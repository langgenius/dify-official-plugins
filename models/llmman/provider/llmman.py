from dify_plugin import ModelProvider


class LlmmanProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        # Credentials are validated per model (customizable-model); nothing at provider level.
        pass
