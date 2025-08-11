from collections.abc import Generator

from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveFileBucket,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleDriveDataSource(OnlineDriveDatasource):
    
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        print(credentials)
        bucket_name = request.bucket
        prefix = request.prefix or "root"
        max_keys = request.max_keys or 5
        next_page_parameters = request.next_page_parameters or {}


        if not credentials:
            raise ValueError("Credentials not found")
        
        
        creds = Credentials.from_authorized_user_info(credentials)
        try:
            service = build("drive", "v3", credentials=creds)

            if next_page_parameters and next_page_parameters.get("page_token"):

                # Call the Drive v3 API
                results = (
                    service.files()
                    .list(q=f"'{prefix}' in parents and trashed = false", 
                        pageSize=max_keys, 
                        fields="nextPageToken, files(id, name, size, mimeType, parents)",
                        pageToken=next_page_parameters.get("page_token"))
                    .execute()
                )
            else:
                results = (
                    service.files()
                    .list(q=f"'{prefix}' in parents and trashed = false", 
                        pageSize=max_keys, 
                        fields="nextPageToken, files(id, name, size, mimeType, parents)")
                    .execute()
                )
            items = results.get("files", [])

            print(results)

            if not items:
                return OnlineDriveBrowseFilesResponse(result=[])
            files = []
            for item in items:
                # Check if it's a folder (Google Drive folders have mimeType 'application/vnd.google-apps.folder')
                is_folder = item.get("mimeType") == "application/vnd.google-apps.folder"
                file_type = "folder" if is_folder else "file"
                size = 0 if is_folder else int(item.get("size", 0))
                files.append(OnlineDriveFile(id=item.get("id", ""), name=item.get("name", ""), size=size, type=file_type))
            next_page_parameters = {"page_token": results.get("nextPageToken", "")} if results.get("nextPageToken") else {}
            is_truncated = results.get("nextPageToken") is not None
            return OnlineDriveBrowseFilesResponse(result=[OnlineDriveFileBucket(bucket=bucket_name, files=files, is_truncated=is_truncated, next_page_parameters=next_page_parameters)])
        except HttpError as error:
            print(f"An error occurred: {error}")
            return OnlineDriveBrowseFilesResponse(result=[])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        file_id = request.id

        if not credentials:
            raise ValueError("Credentials not found")
            
        creds = Credentials.from_authorized_user_info(credentials)
        try:
            service = build("drive", "v3", credentials=creds)
            # Get file metadata first
            file_metadata = service.files().get(fileId=file_id).execute()
            # Download file content
            file_content = service.files().get_media(fileId=file_id).execute()
            yield self.create_blob_message(file_content, meta={"file_name": file_metadata.get("name"), "mime_type": file_metadata.get("mimeType")})
        except HttpError as error:
            raise error


