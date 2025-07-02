import json
from collections.abc import Generator
from typing import Any

from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveFileBucket,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource
from google.cloud import storage
from google.oauth2 import service_account


class GoogleCloudStorageDataSource(OnlineDriveDatasource):
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials.get("credentials")
        bucket_name = request.bucket
        prefix = request.prefix or ""
        max_keys = request.max_keys or 100
        start_after = request.start_after or ""


        if not credentials or not bucket_name:
            raise ValueError("Credentials or bucket not found")

        creds = service_account.Credentials.from_service_account_info(json.loads(credentials))
        client = storage.Client(credentials=creds)
        blobs = client.list_blobs(bucket_name, prefix=prefix, max_results=max_keys, start_offset=start_after)
        is_truncated = blobs.next_page_token is not None
        pages = [OnlineDriveFile(key=blob.name, size=blob.size) for blob in blobs if not blob.name.endswith('/')]

        file_bucket = OnlineDriveFileBucket(bucket=bucket_name, files=pages, is_truncated=is_truncated)
        return OnlineDriveBrowseFilesResponse(files=[file_bucket])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials.get("credentials")
        bucket_name = request.bucket
        key = request.key
        if not credentials or not bucket_name:
            raise ValueError("Credentials or bucket not found")

        creds = service_account.Credentials.from_service_account_info(json.loads(credentials))
        client = storage.Client(credentials=creds)
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(key)
        b64bytes = blob.download_as_bytes()

        yield self.create_blob_message(key, b64bytes)