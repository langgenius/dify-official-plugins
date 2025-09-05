from typing import Any, Mapping

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider
from qcloud_cos import CosConfig, CosS3Client


class TencentCOSStorageProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            if not credentials or not credentials.get("secret_key"):
                raise ToolProviderCredentialValidationError(
                    "Tencent COS Storage secret key is required."
                )
            if not credentials.get("secret_id"):
                raise ToolProviderCredentialValidationError(
                    "Tencent COS Storage secret ID is required."
                )
            if not credentials.get("region"):
                raise ToolProviderCredentialValidationError(
                    "Tencent COS Storage region is required."
                )

            config = CosConfig(
                Region=credentials.get("region"),
                SecretId=credentials.get("secret_id"),
                SecretKey=credentials.get("secret_key"),
                Scheme="https",
            )
            client = CosS3Client(config)
            # Test the connection by listing buckets
            client.list_buckets()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
