"""TypeSafe AI provider with one explicit API-key credential."""

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType

from models.llm.llm import MODEL


class TypeSafeAIProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        self.get_model_instance(ModelType.LLM).validate_credentials(MODEL, credentials)
