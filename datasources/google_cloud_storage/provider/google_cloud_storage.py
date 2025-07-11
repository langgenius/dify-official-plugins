import json
from typing import Any, Mapping

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider
from google.cloud import storage
from google.oauth2 import service_account


class GoogleCloudStorageDatasourceProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            if not credentials or not credentials.get("credentials"):
                raise ToolProviderCredentialValidationError(
                    "Google Cloud Storage credentials are required."
                )
            if not isinstance(credentials.get("credentials"), str):
                raise ToolProviderCredentialValidationError(
                    "Google Cloud Storage credentials must be a string json."
                )
            
            service_account_obj = json.loads(credentials.get("credentials"))
            google_client = storage.Client.from_service_account_info(service_account_obj)
            google_client.list_buckets()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
