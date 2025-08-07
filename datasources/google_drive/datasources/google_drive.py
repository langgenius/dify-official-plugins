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
from google.cloud import storage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleCloudStorageDataSource(OnlineDriveDatasource):
    
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        print(credentials)
        bucket_name = request.bucket
        prefix = request.prefix or ""
        max_keys = 5
        start_after = request.start_after or ""


        if not credentials:
            raise ValueError("Credentials not found")
        
        
        creds = Credentials.from_authorized_user_info(credentials)
        try:
            service = build("drive", "v3", credentials=creds)

            # Call the Drive v3 API
            results = (
                service.files()
                .list(q="'19WXBlOt3GW9hzBHevD--utkExH4cIqoP' in parents and trashed = false", pageSize=max_keys, fields="nextPageToken, files(id, name, size, mimeType, parents)")
                .execute()
            )
            items = results.get("files", [])

            print(results)

            if not items:
                return OnlineDriveBrowseFilesResponse(result=[])
            files = []
            for item in items:
                files.append(OnlineDriveFile(key=item.get("name", ""), size=item.get("size", 0)))
            return OnlineDriveBrowseFilesResponse(result=[OnlineDriveFileBucket(bucket=bucket_name, files=files, is_truncated=False)])
        except HttpError as error:
            print(f"An error occurred: {error}")
            return OnlineDriveBrowseFilesResponse(result=[])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials.get("credentials")
        bucket_name = request.bucket
        key = request.key

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