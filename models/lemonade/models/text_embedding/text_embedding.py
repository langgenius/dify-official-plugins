from typing import Mapping
import json
import requests
from urllib.parse import urljoin

from dify_plugin.entities.model import AIModelEntity, I18nObject
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.openai_compatible.text_embedding import OAICompatEmbeddingModel


class LemonadeTextEmbeddingModel(OAICompatEmbeddingModel):

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        credentials = credentials or {}
        entity = super().get_customizable_model_schema(model, credentials)

        return entity

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials for Lemonade text embedding API.

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            headers = {"Content-Type": "application/json"}

            # Lemonade provider uses a fixed API key
            headers["Authorization"] = "Bearer lemonade"

            endpoint_url = credentials.get("endpoint_url")
            if not endpoint_url:
                raise CredentialsValidateFailedError("endpoint_url is required")
            
            if not endpoint_url.endswith("/"):
                endpoint_url += "/"

            endpoint_url = urljoin(endpoint_url, "api/v1/embeddings")

            payload = {"input": "ping", "model": model}

            response = requests.post(url=endpoint_url, headers=headers, data=json.dumps(payload), timeout=(10, 300))

            if response.status_code != 200:
                raise CredentialsValidateFailedError(
                    f"Credentials validation failed with status code {response.status_code}"
                )

            try:
                json_result = response.json()
            except json.JSONDecodeError as e:
                raise CredentialsValidateFailedError("Credentials validation failed: JSON decode error")

            if "data" not in json_result:
                raise CredentialsValidateFailedError("Credentials validation failed: invalid response format")

        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))
