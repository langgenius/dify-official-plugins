from dify_plugin.model.provider import ModelProvider

class DeepInfraProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        pass