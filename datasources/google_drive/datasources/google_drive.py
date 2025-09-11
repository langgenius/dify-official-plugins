import logging
from collections.abc import Generator

import requests
from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveFileBucket,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource

logger = logging.getLogger(__name__)


class GoogleDriveDataSource(OnlineDriveDatasource):
    _BASE_URL = "https://www.googleapis.com/drive/v3"
    
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        prefix = request.prefix or "root"
        max_keys = request.max_keys or 10
        next_page_parameters = request.next_page_parameters or {}

        if not credentials:
            raise ValueError("Credentials not found")
        
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        # Prepare headers for HTTP request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        # Build query parameters
        params = {
            "q": f"'{prefix}' in parents and trashed = false",
            "pageSize": max_keys,
            "fields": "nextPageToken, files(id, name, size, mimeType, parents)"
        }
        
        # Add page token if exists
        if next_page_parameters and next_page_parameters.get("page_token"):
            params["pageToken"] = next_page_parameters.get("page_token")
        
        try:
            # Make HTTP request to Google Drive API
            url = f"{self._BASE_URL}/files"
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Check for authentication errors
            if response.status_code == 401:
                raise ValueError(
                    "Authentication failed (401 Unauthorized). The access token may have expired. "
                    "Please refresh or reauthorize the connection."
                )
            elif response.status_code != 200:
                raise ValueError(f"Failed to list files: {response.status_code} - {response.text[:200]}")
            
            # Parse response
            results = response.json()
            items = results.get("files", [])
            
            if not items:
                return OnlineDriveBrowseFilesResponse(result=[])
            
            files = []
            for item in items:
                # Check if it's a folder (Google Drive folders have mimeType 'application/vnd.google-apps.folder')
                is_folder = item.get("mimeType") == "application/vnd.google-apps.folder"
                file_type = "folder" if is_folder else "file"
                size = 0 if is_folder else int(item.get("size", 0))
                files.append(OnlineDriveFile(
                    id=item.get("id", ""), 
                    name=item.get("name", ""), 
                    size=size, 
                    type=file_type
                ))
            
            # Handle pagination
            next_page_token = results.get("nextPageToken")
            next_page_parameters = {"page_token": next_page_token} if next_page_token else {}
            is_truncated = next_page_token is not None
            
            return OnlineDriveBrowseFilesResponse(result=[
                OnlineDriveFileBucket(
                    bucket=bucket_name, 
                    files=files, 
                    is_truncated=is_truncated, 
                    next_page_parameters=next_page_parameters
                )
            ])
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Network error when accessing Google Drive: {str(e)}") from e
        except Exception as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                raise ValueError(
                    "Authentication failed. The access token may have expired. "
                    "Please refresh or reauthorize the connection."
                ) from e
            return OnlineDriveBrowseFilesResponse(result=[])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        file_id = request.id

        if not credentials:
            raise ValueError("Credentials not found")
        
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        logger.debug(f"Downloading file with ID: {file_id}")
        
        # Prepare headers for HTTP request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            # First, get file metadata
            metadata_url = f"{self._BASE_URL}/files/{file_id}"
            metadata_params = {"fields": "id,name,mimeType,size"}
            
            metadata_response = requests.get(
                metadata_url, 
                headers=headers, 
                params=metadata_params,
                timeout=30
            )
            
            if metadata_response.status_code == 401:
                logger.error(f"Authentication failed: {metadata_response.text[:200]}")
                raise ValueError(
                    "Authentication failed (401 Unauthorized). The access token may have expired. "
                    "Please refresh or reauthorize the connection."
                )
            elif metadata_response.status_code == 404:
                logger.error(f"File not found: {file_id}")
                raise ValueError(f"File with ID '{file_id}' not found.")
            elif metadata_response.status_code != 200:
                logger.error(f"Failed to get file metadata: {metadata_response.status_code}")
                raise ValueError(f"Failed to get file metadata: {metadata_response.status_code}")
            
            file_metadata = metadata_response.json()
            file_name = file_metadata.get("name", "unknown")
            mime_type = file_metadata.get("mimeType", "application/octet-stream")
                        
            # Check if it's a Google Workspace file (Docs, Sheets, etc.)
            is_google_workspace_file = mime_type.startswith("application/vnd.google-apps.")
            
            if is_google_workspace_file:
                # Google Workspace files need to be exported
                export_mime_type = self._get_export_mime_type(mime_type)
                content_url = f"{self._BASE_URL}/files/{file_id}/export"
                content_params = {"mimeType": export_mime_type}
                
            else:
                # Regular files can be downloaded directly
                content_url = f"{self._BASE_URL}/files/{file_id}"
                content_params = {"alt": "media"}
            
            # Download file content
            content_response = requests.get(
                content_url,
                headers=headers,
                params=content_params,
                timeout=60,  # Longer timeout for file downloads
                stream=True  # Stream the response for large files
            )
            
            if content_response.status_code == 401:
                logger.error("Authentication failed during file download")
                raise ValueError(
                    "Authentication failed during file download. "
                    "Please refresh or reauthorize the connection."
                )
            elif content_response.status_code != 200:
                logger.error(f"Failed to download file: {content_response.status_code}")
                raise ValueError(f"Failed to download file: {content_response.status_code}")
            
            # Get the content
            file_content = content_response.content
            
            # For exported Google Workspace files, update the mime type
            if is_google_workspace_file:
                mime_type = self._get_export_mime_type(mime_type)
            
            yield self.create_blob_message(file_content, meta={
                "file_name": file_name,
                "mime_type": mime_type
            })
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            raise ValueError(f"Network error when downloading file: {str(e)}") from e
        except Exception as e:
            if "already" not in str(e).lower():  # Avoid re-raising our own errors
                logger.error(f"Unexpected error: {e}")
            raise
    
    def _get_export_mime_type(self, google_mime_type: str) -> str:
        """Convert Google Workspace MIME types to exportable formats."""
        export_mapping = {
            "application/vnd.google-apps.document": "application/pdf",  # Google Docs to PDF
            "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # Google Sheets to Excel
            "application/vnd.google-apps.presentation": "application/pdf",  # Google Slides to PDF
            "application/vnd.google-apps.drawing": "image/png",  # Google Drawings to PNG
            "application/vnd.google-apps.form": "application/pdf",  # Google Forms to PDF
        }
        return export_mapping.get(google_mime_type, "application/pdf")  # Default to PDF