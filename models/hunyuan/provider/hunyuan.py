import logging
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class HunyuanProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            secret_id = credentials.get("secret_id")
            secret_key = credentials.get("secret_key")
            tokenhub_api_key = (credentials.get("tokenhub_api_key") or "").strip()
            if bool(secret_id) != bool(secret_key):
                raise CredentialsValidateFailedError("Enter both the Tencent Cloud Secret ID and Secret Key.")
            if not (secret_id or tokenhub_api_key):
                raise CredentialsValidateFailedError(
                    "Enter a TokenHub API key or a Tencent Cloud Secret ID and Secret Key."
                )

            if tokenhub_api_key:
                model_instance = self.get_model_instance(ModelType.LLM)
                model_instance.validate_credentials(model="hy4", credentials=credentials)
            else:
                model_instance = self.get_model_instance(ModelType.TEXT_EMBEDDING)
                model_instance.validate_credentials(model="lke-text-embedding-v1", credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex
