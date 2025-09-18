from typing import Any, Mapping

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider
import boto3  # type: ignore
from botocore.client import Config  # type: ignore


class GoogleCloudStorageDatasourceProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            if not credentials or not credentials.get("secret_access_key"):
                raise ToolProviderCredentialValidationError(
                    "AWS S3 Storage credentials are required."
                )
            if not credentials.get("access_key_id"):
                raise ToolProviderCredentialValidationError(
                    "AWS S3 Storage access key is required."
                )
            if not credentials.get("region_name"):
                raise ToolProviderCredentialValidationError(
                    "AWS S3 Storage region is required."
                )
            
            client = boto3.client(
                "s3",
                aws_secret_access_key=credentials.get("secret_access_key"),
                aws_access_key_id=credentials.get("access_key_id"),
                endpoint_url=f"https://s3.{credentials.get('region_name')}.amazonaws.com",
                region_name=credentials.get("region_name"),
                config=Config(s3={"addressing_style": "path"}),
            )
            client.list_buckets()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))