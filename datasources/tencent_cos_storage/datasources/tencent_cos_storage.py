import os
from collections.abc import Generator
from qcloud_cos import CosConfig, CosS3Client
from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveFileBucket,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource


class TencentCOSStorageDataSource(OnlineDriveDatasource):
    def _browse_files(
        self, request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        prefix = request.prefix or ""
        max_keys = request.max_keys or 100
        next_page_parameters = request.next_page_parameters or {}

        if not credentials:
            raise ValueError("Credentials not found")

        config = CosConfig(
            Region=credentials.get("region"),
            SecretId=credentials.get("secret_id"),
            SecretKey=credentials.get("secret_key"),
            Scheme="https",
        )
        client = CosS3Client(config)

        if not bucket_name:
            response = client.list_buckets()
            buckets = response.get("Buckets", {}).get("Bucket", [])
            file_buckets = [
                OnlineDriveFileBucket(
                    bucket=bucket["Name"],
                    files=[],
                    is_truncated=False,
                    next_page_parameters={},
                )
                for bucket in buckets
            ]
            return OnlineDriveBrowseFilesResponse(result=file_buckets)
        else:
            if not next_page_parameters and prefix:
                max_keys = max_keys + 1
            marker = next_page_parameters.get("marker")

            kwargs = {
                "Bucket": bucket_name,
                "Prefix": prefix,
                "MaxKeys": max_keys,
                "Delimiter": "/",
            }
            if marker:
                kwargs["Marker"] = marker

            response = client.list_objects(**kwargs)

            is_truncated = response.get("IsTruncated", False)
            next_marker = response.get("NextMarker")
            next_page_parameters = {"marker": next_marker} if next_marker else {}

            files = []
            # Add files
            for obj in response.get("Contents", []):
                if obj["Key"] != prefix:  # Skip the prefix itself
                    files.append(
                        OnlineDriveFile(
                            id=obj["Key"],
                            name=os.path.basename(obj["Key"]),
                            size=obj["Size"],
                            type="file",
                        )
                    )

            # Add folders
            for prefix_obj in response.get("CommonPrefixes", []):
                folder_name = os.path.basename(prefix_obj["Prefix"].rstrip("/"))
                files.append(
                    OnlineDriveFile(
                        id=prefix_obj["Prefix"], name=folder_name, size=0, type="folder"
                    )
                )

            file_bucket = OnlineDriveFileBucket(
                bucket=bucket_name,
                files=sorted(files, key=lambda x: x.id),
                is_truncated=is_truncated,
                next_page_parameters=next_page_parameters,
            )
            return OnlineDriveBrowseFilesResponse(result=[file_bucket])

    def _download_file(
        self, request: OnlineDriveDownloadFileRequest
    ) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        key = request.id

        if not credentials:
            raise ValueError("Credentials not found")

        if not bucket_name:
            raise ValueError("Bucket name not found")

        config = CosConfig(
            Region=credentials.get("region"),
            SecretId=credentials.get("secret_id"),
            SecretKey=credentials.get("secret_key"),
            Scheme="https",
        )
        client = CosS3Client(config)

        response = client.get_object(Bucket=bucket_name, Key=key)
        content = response["Body"].get_raw_stream().read()

        # Get content type from response headers
        content_type = response.get("Content-Type", "application/octet-stream")
        yield self.create_blob_message(
            content, meta={"file_name": key, "mime_type": content_type}
        )
