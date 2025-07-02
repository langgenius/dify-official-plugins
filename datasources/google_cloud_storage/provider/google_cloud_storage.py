import json
from typing import Any, Mapping

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider
from google.cloud import storage
from google.oauth2 import service_account


class GoogleCloudStorageDatasourceProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            if "credentials" not in credentials or not credentials.get("credentials"):
                raise ToolProviderCredentialValidationError(
                    "Google Cloud Storage credentials are required."
                )
            if "bucket" not in credentials or not credentials.get("bucket"):
                raise ToolProviderCredentialValidationError(
                    "Google Cloud Storage bucket is required."
                )

            creds = service_account.Credentials.from_service_account_info(
                json.loads(credentials.get("credentials"))
            )
            client = storage.Client(credentials=creds)
            client.get_bucket(credentials.get("bucket"))
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
