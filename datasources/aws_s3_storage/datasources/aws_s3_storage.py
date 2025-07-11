from calendar import c
import json
from collections.abc import Generator
from typing import Any, Mapping

from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveFileBucket,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveBrowseFilesResponse,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource
import boto3  # type: ignore
from botocore.client import Config  # type: ignore


class AWSS3StorageDataSource(OnlineDriveDatasource):
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        prefix = request.prefix or ""
        max_keys = request.max_keys or 100
        start_after = request.start_after or ""
        print(credentials)

        if not credentials:
            raise ValueError("Credentials not found")
        
        client = boto3.client(
            "s3",
            aws_secret_access_key=credentials.get("secret_access_key"),
            aws_access_key_id=credentials.get("access_key_id"),
            endpoint_url=f"https://s3.{credentials.get('region_name')}.amazonaws.com",
            region_name=credentials.get("region_name"),
            config=Config(s3={"addressing_style": "path"}),
        )
        if not bucket_name:
            response = client.list_buckets()
            file_buckets = [OnlineDriveFileBucket(bucket=bucket["Name"], files=[], is_truncated=False) for bucket in response["Buckets"]]
            return OnlineDriveBrowseFilesResponse(result=file_buckets)
        else:
            if not start_after and prefix:
                max_keys = max_keys + 1
            response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, MaxKeys=max_keys, StartAfter=start_after, Delimiter="/")
            is_truncated = response.get("IsTruncated", False)
            files = []
            files.extend([OnlineDriveFile(key=blob["Key"], size=blob["Size"]) for blob in response.get("Contents", []) if blob["Key"]!=prefix])
            for prefix in response.get("CommonPrefixes", []):
                files.append(OnlineDriveFile(key=prefix["Prefix"], size=0))
            file_bucket = OnlineDriveFileBucket(bucket=bucket_name, files=sorted(files, key=lambda x: x.key), is_truncated=is_truncated)
            return OnlineDriveBrowseFilesResponse(result=[file_bucket])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        key = request.key

        if not credentials:
            raise ValueError("Credentials not found")
        
        if not bucket_name:
            raise ValueError("Bucket name not found")

        client = boto3.client(
            "s3",
            aws_secret_access_key=credentials.get("secret_access_key"),
            aws_access_key_id=credentials.get("access_key_id"),
            endpoint_url=f"https://s3.{credentials.get('region_name')}.amazonaws.com",
            region_name=credentials.get("region_name"),
            config=Config(s3={"addressing_style": "path"}),
        )
        response = client.get_object(Bucket=bucket_name, Key=key)
        b64bytes = response["Body"].read()

        yield self.create_blob_message(b64bytes, meta={"file_name": key, "mime_type": response["ContentType"]})
