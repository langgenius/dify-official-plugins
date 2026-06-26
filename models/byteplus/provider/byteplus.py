from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType


class BytePlusProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        model_instance = self.get_model_instance(ModelType.LLM)
        model_instance.validate_credentials(
            model="seedance-2-0-260128",
            credentials=credentials,
        )
