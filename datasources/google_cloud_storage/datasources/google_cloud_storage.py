import json
import os
from collections.abc import Generator
from typing import Any, Mapping

from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveFileBucket,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource
from google.cloud import storage


class GoogleCloudStorageDataSource(OnlineDriveDatasource):
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials.get("credentials")
        bucket_name = request.bucket
        prefix = request.prefix or ""
        max_keys = request.max_keys or 100
        next_page_parameters = request.next_page_parameters or {}


        if not credentials:
            raise ValueError("Credentials not found")
        
        
        client = storage.Client.from_service_account_info(json.loads(credentials))
        if not bucket_name:
            buckets = client.list_buckets()
            file_buckets = [OnlineDriveFileBucket(bucket=bucket.name, files=[], is_truncated=False, next_page_parameters={}) for bucket in buckets]
            return OnlineDriveBrowseFilesResponse(result=file_buckets)
        else:
            if not next_page_parameters and prefix:
                max_keys = max_keys + 1
            blobs = client.list_blobs(bucket_name, 
                                      prefix=prefix, 
                                      max_results=max_keys, 
                                      page_token=next_page_parameters.get("page_token"), 
                                      delimiter="/")
            is_truncated = blobs.next_page_token is not None
            next_page_parameters = {"page_token": blobs.next_page_token} if blobs.next_page_token else {}
            files = []
            files.extend([OnlineDriveFile(id=blob.name, name=os.path.basename(blob.name), size=blob.size, type="file") for blob in blobs if blob.name!=prefix])
            for prefix in blobs.prefixes:
                if next_page_parameters and next_page_parameters == prefix:
                    continue
                files.append(OnlineDriveFile(id=prefix, name=os.path.basename(prefix.rstrip('/')), size=0, type="folder"))
            file_bucket = OnlineDriveFileBucket(bucket=bucket_name, files=sorted(files, key=lambda x: x.id), is_truncated=is_truncated, next_page_parameters=next_page_parameters)
            return OnlineDriveBrowseFilesResponse(result=[file_bucket])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials.get("credentials")
        bucket_name = request.bucket
        key = request.id

        if not credentials:
            raise ValueError("Credentials not found")
        
        if not bucket_name:
            raise ValueError("Bucket name not found")

        client = storage.Client.from_service_account_info(json.loads(credentials))
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(key)
        b64bytes = blob.download_as_bytes()
        yield self.create_blob_message(b64bytes, meta={"file_name": key, "mime_type": blob.content_type})

    def _get_service_account_obj(self, credentials: Mapping[str, Any]) -> dict:
        service_account_obj = {
            key: credentials.get(key)
            for key in [
                "project_id", "private_key_id", "private_key", 
                "client_email", "client_id", "client_x509_cert_url"
            ]
        }

        service_account_obj.update({
            "type": "service_account",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "universe_domain": "googleapis.com",
        })

        return service_account_obj