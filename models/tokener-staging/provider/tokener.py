from dify_plugin import ModelProvider

from models._credentials import validate_model_access


class TokenerModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        validate_model_access(credentials)
