import logging
import os
from collections.abc import Generator

import dropbox
from dropbox.exceptions import AuthError, ApiError
from dropbox.files import FileMetadata, FolderMetadata

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


class DropboxDataSource(OnlineDriveDatasource):
    
    def _get_dropbox_client(self) -> dropbox.Dropbox:
        """Get authenticated Dropbox client"""
        credentials = self.runtime.credentials
        if not credentials:
            raise ValueError("Credentials not found")
        
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        try:
            dbx = dropbox.Dropbox(access_token)
            # Verify the connection
            dbx.users_get_current_account()
            return dbx
        except AuthError as e:
            raise ValueError(f"Authentication failed: {str(e)}") from e
    
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        bucket_name = request.bucket or ""  # Dropbox doesn't have buckets, use empty string
        prefix = request.prefix or ""  # Start from root if no prefix
        max_keys = request.max_keys or 100
        next_page_parameters = request.next_page_parameters or {}
        
        try:
            dbx = self._get_dropbox_client()
            
            # Handle file IDs vs paths
            if prefix and prefix.startswith("id:"):
                # Convert file ID to path
                try:
                    metadata = dbx.files_get_metadata(prefix)
                    if isinstance(metadata, FolderMetadata):
                        # It's a folder, use its path
                        path = metadata.path_display
                    else:
                        # It's a file, can't list contents of a file
                        raise ValueError(f"Cannot browse contents of file: {metadata.name}")
                except ApiError as e:
                    error_str = str(e)
                    if "not_found" in error_str:
                        raise ValueError(f"Item with ID '{prefix}' not found") from e
                    else:
                        raise ValueError(f"Failed to resolve ID '{prefix}': {error_str}") from e
            else:
                # Build the path to list
                path = prefix if prefix else ""
                if path and not path.startswith("/"):
                    path = "/" + path
                if path == "/":
                    path = ""  # Root folder should be empty string
            
            # Handle pagination
            cursor = next_page_parameters.get("cursor")
            
            try:
                if cursor:
                    # Continue from previous listing
                    result = dbx.files_list_folder_continue(cursor)
                else:
                    # Start new listing
                    result = dbx.files_list_folder(path, limit=max_keys)
                
                files = []
                for entry in result.entries:
                    file_info = {
                        "id": entry.id,
                        "name": entry.name,
                        "path": entry.path_display,
                    }
                    
                    if isinstance(entry, FileMetadata):
                        file_info.update({
                            "type": "file",
                            "size": entry.size,
                            "modified": entry.server_modified.isoformat() if entry.server_modified else None,
                        })
                    elif isinstance(entry, FolderMetadata):
                        file_info.update({
                            "type": "folder", 
                            "size": 0,
                        })
                    
                    files.append(OnlineDriveFile(
                        id=file_info["id"],
                        name=file_info["name"],
                        size=file_info["size"],
                        type=file_info["type"]
                    ))
                
                # Handle pagination
                next_cursor = result.cursor if result.has_more else None
                next_page_parameters = {"cursor": next_cursor} if next_cursor else {}
                is_truncated = result.has_more
                
                return OnlineDriveBrowseFilesResponse(result=[
                    OnlineDriveFileBucket(
                        bucket=bucket_name,
                        files=files,
                        is_truncated=is_truncated,
                        next_page_parameters=next_page_parameters
                    )
                ])
                
            except ApiError as e:
                error_str = str(e)
                if "not_found" in error_str:
                    raise ValueError(f"Path '{path}' not found") from e
                elif "malformed_path" in error_str:
                    raise ValueError(f"Invalid path format: '{path}'") from e
                elif "invalid_cursor" in error_str:
                    raise ValueError("Invalid pagination cursor") from e
                else:
                    raise ValueError(f"Dropbox API error: {error_str}") from e
                    
        except AuthError as e:
            raise ValueError(
                "Authentication failed. The access token may have expired. "
                "Please refresh or reauthorize the connection."
            ) from e
        except Exception as e:
            if "Authentication failed" in str(e):
                raise
            logger.error(f"Error browsing Dropbox files: {e}")
            raise ValueError(f"Failed to browse Dropbox files: {str(e)}") from e

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        file_id = request.id
        
        if not file_id:
            raise ValueError("File ID is required")
        
        try:
            dbx = self._get_dropbox_client()
            
            # First, get file metadata using the file ID
            try:
                # Get file metadata by ID
                metadata_result = dbx.files_get_metadata(file_id)
                
                if not isinstance(metadata_result, FileMetadata):
                    raise ValueError("The specified ID is not a file")
                
                file_name = metadata_result.name
                file_size = metadata_result.size
                
                # Use the path_display for downloading since Dropbox download API requires path
                file_path = metadata_result.path_display
                
            except ApiError as e:
                error_str = str(e)
                if "not_found" in error_str:
                    raise ValueError(f"File with ID '{file_id}' not found") from e
                else:
                    raise ValueError(f"Failed to get file metadata: {error_str}") from e
            
            # Download the file content
            try:
                _, response = dbx.files_download(file_path)
                file_content = response.content
                
                # Determine MIME type based on file extension
                mime_type = self._get_mime_type(file_name)
                
                logger.debug(f"Downloaded file: {file_name} (size: {file_size} bytes)")
                
                yield self.create_blob_message(file_content, meta={
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "file_size": file_size
                })
                
            except ApiError as e:
                error_str = str(e)
                if "not_found" in error_str:
                    raise ValueError(f"File '{file_path}' not found") from e
                elif "insufficient_space" in error_str:
                    raise ValueError("Insufficient space to download file") from e
                else:
                    raise ValueError(f"Failed to download file: {error_str}") from e
                    
        except AuthError as e:
            raise ValueError(
                "Authentication failed during file download. "
                "Please refresh or reauthorize the connection."
            ) from e
        except Exception as e:
            if "Authentication failed" in str(e) or "not found" in str(e).lower():
                raise
            logger.error(f"Unexpected error downloading file: {e}")
            raise ValueError(f"Error downloading file: {str(e)}") from e
    
    def _get_mime_type(self, file_name: str) -> str:
        """Determine MIME type based on file extension"""
        if not file_name:
            return "application/octet-stream"
        
        ext = os.path.splitext(file_name.lower())[1]
        
        mime_types = {
            '.txt': 'text/plain',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.tar': 'application/x-tar',
            '.gz': 'application/gzip',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.py': 'text/x-python',
            '.java': 'text/x-java-source',
            '.cpp': 'text/x-c++src',
            '.c': 'text/x-csrc',
            '.h': 'text/x-chdr',
        }
        
        return mime_types.get(ext, 'application/octet-stream')