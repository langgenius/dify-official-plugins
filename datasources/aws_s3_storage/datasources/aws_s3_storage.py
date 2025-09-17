import os
from collections.abc import Generator
import boto3
from botocore.client import Config
from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveFileBucket,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource


class AWSS3StorageDataSource(OnlineDriveDatasource):
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        prefix = request.prefix or ""
        max_keys = request.max_keys or 100
        next_page_parameters = request.next_page_parameters or {}

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
            file_buckets = [OnlineDriveFileBucket(bucket=bucket["Name"], files=[], is_truncated=False, next_page_parameters={}) for bucket in response["Buckets"]]
            return OnlineDriveBrowseFilesResponse(result=file_buckets)
        else:
            if not next_page_parameters and prefix:
                max_keys = max_keys + 1
            continuation_token = next_page_parameters.get("continuation_token")
            if continuation_token:
                response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, MaxKeys=max_keys, ContinuationToken=continuation_token, Delimiter="/")
            else:
                response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, MaxKeys=max_keys, Delimiter="/")
            is_truncated = response.get("IsTruncated", False)
            next_continuation_token = response.get("NextContinuationToken")
            next_page_parameters = {"continuation_token": next_continuation_token} if next_continuation_token else {}
            files = []
            files.extend([OnlineDriveFile(id=blob["Key"], name=os.path.basename(blob["Key"]), size=blob["Size"], type="file") for blob in response.get("Contents", []) if blob["Key"]!=prefix])
            for prefix in response.get("CommonPrefixes", []):
                files.append(OnlineDriveFile(id=prefix["Prefix"], name=os.path.basename(prefix["Prefix"].rstrip('/')), size=0, type="folder"))
            file_bucket = OnlineDriveFileBucket(bucket=bucket_name, files=sorted(files, key=lambda x: x.id), is_truncated=is_truncated, next_page_parameters=next_page_parameters)
            return OnlineDriveBrowseFilesResponse(result=[file_bucket])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        key = request.id

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
