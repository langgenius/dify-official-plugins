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


class BoxDataSource(OnlineDriveDatasource):
    _BASE_URL = "https://api.box.com/2.0"

    def _browse_files(
        self, request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        prefix = request.prefix or ""  # Allow empty prefix for root folder
        max_keys = request.max_keys or 10
        next_page_parameters = request.next_page_parameters or {}

        if not credentials:
            raise ValueError("Credentials not found")
        
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        # Resolve prefix to folder ID if it's a path
        try:
            # folder_id = self._resolve_folder_path_to_id(prefix, access_token)
            # logger.debug(f"Resolved prefix '{prefix}' to folder ID: {folder_id}")
            if not prefix or prefix.strip() == "":
                folder_id = "0"
            else:
                folder_id = prefix
        except Exception as e:
            logger.error(f"Failed to resolve folder path '{prefix}': {str(e)}")
            raise ValueError(f"Failed to resolve folder path '{prefix}': {str(e)}")
        
        # Prepare headers for HTTP request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        # Build query parameters for Box API
        params = {
            "limit": max_keys,
            "fields": "id,name,size,type,modified_at"
        }
        
        # Add offset for pagination if exists
        if next_page_parameters and next_page_parameters.get("offset"):
            params["offset"] = next_page_parameters.get("offset")
        
        try:
            # Make HTTP request to Box API
            url = f"{self._BASE_URL}/folders/{folder_id}/items"
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Check for authentication errors
            if response.status_code == 401:
                raise ValueError(
                    "Authentication failed (401 Unauthorized). The access token may have expired. "
                    "Please refresh or reauthorize the connection."
                )
            elif response.status_code == 404:
                raise ValueError(f"Folder with ID '{folder_id}' not found.")
            elif response.status_code != 200:
                raise ValueError(f"Failed to list files: {response.status_code} - {response.text[:200]}")
            
            # Parse response
            results = response.json()
            items = results.get("entries", [])
            
            if not items:
                return OnlineDriveBrowseFilesResponse(result=[])
            
            files = []
            for item in items:
                # Check if it's a folder (Box folders have type 'folder')
                is_folder = item.get("type") == "folder"
                file_type = "folder" if is_folder else "file"
                size = 0 if is_folder else int(item.get("size", 0))
                files.append(OnlineDriveFile(
                    id=item.get("id", ""), 
                    name=item.get("name", ""), 
                    size=size, 
                    type=file_type
                ))
            
            # Handle pagination - Box uses offset-based pagination
            total_count = results.get("total_count", 0)
            offset = results.get("offset", 0)
            limit = results.get("limit", max_keys)
            
            # Calculate if there are more items
            has_more = offset + limit < total_count
            next_offset = offset + limit if has_more else None
            next_page_parameters = {"offset": next_offset} if next_offset else {}
            is_truncated = has_more
            
            return OnlineDriveBrowseFilesResponse(result=[
                OnlineDriveFileBucket(
                    bucket=bucket_name, 
                    files=files, 
                    is_truncated=is_truncated, 
                    next_page_parameters=next_page_parameters
                )
            ])
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Network error when accessing Box: {str(e)}") from e
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
            metadata_params = {"fields": "id,name,size,type"}
            
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
            file_type = file_metadata.get("type", "file")
            
            # Check if it's a folder
            if file_type == "folder":
                raise ValueError(f"Cannot download folder '{file_name}'. Please select a file.")
            
            # Get file content URL
            content_url = f"{self._BASE_URL}/files/{file_id}/content"
            
            # Download file content
            content_response = requests.get(
                content_url,
                headers=headers,
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
            
            # Determine MIME type from file extension or use default
            mime_type = self._get_mime_type_from_filename(file_name)
            
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
    
    def _get_mime_type_from_filename(self, filename: str) -> str:
        """Determine MIME type from file extension."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"