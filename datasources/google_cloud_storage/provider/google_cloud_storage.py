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

            bucket_names_raw = credentials.get("bucket_names", "").strip()
            if bucket_names_raw:
                bucket_names = [name.strip() for name in bucket_names_raw.split(",") if name.strip()]
                if not bucket_names:
                    raise ToolProviderCredentialValidationError(
                        "bucket_names is specified but contains no valid bucket names."
                    )
                failed_buckets = []
                for name in bucket_names:
                    try:
                        list(google_client.list_blobs(name, max_results=1))
                    except Exception as e:
                        failed_buckets.append(f"{name}: {e}")
                if failed_buckets:
                    raise ToolProviderCredentialValidationError(
                        "Failed to access the following bucket(s):\n" + "\n".join(failed_buckets)
                    )
            else:
                google_client.list_buckets()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
