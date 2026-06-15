from dify_plugin.model.provider import ModelProvider
class DeepInfraProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        if not credentials.get("api_key"):
            raise ValueError("API key required")