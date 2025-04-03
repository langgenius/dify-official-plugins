"""
Dropbox utilities module.
Contains common functionality used across Dropbox tools.
"""
import io
import os
from typing import Dict, List, Any, Optional, Union, BinaryIO

import dropbox
from dropbox.files import FileMetadata, FolderMetadata, ListFolderResult
from dropbox.exceptions import ApiError, AuthError


class DropboxUtils:
    """Utilities for Dropbox operations."""

    @staticmethod
    def get_client(access_token: str) -> dropbox.Dropbox:
        """
        Get authenticated Dropbox client
        
        Args:
            access_token: Dropbox access token
            
        Returns:
            Dropbox client object
            
        Raises:
            AuthError: If authentication fails
        """
        try:
            dbx = dropbox.Dropbox(access_token)
            # Verify the connection
            dbx.users_get_current_account()
            return dbx
        except AuthError as e:
            raise AuthError("Invalid access token or authentication failed", e)
    
    @staticmethod
    def list_folder(dbx: dropbox.Dropbox, path: str = "") -> List[Dict[str, Any]]:
        """
        List files and folders in a specified Dropbox folder
        
        Args:
            dbx: Authenticated Dropbox client
            path: Path to list (default: root)
            
        Returns:
            List of dictionaries with file/folder details
            
        Raises:
            ApiError: If there's an issue with the API call
        """
        try:
            result = dbx.files_list_folder(path)
            items = []
            
            for entry in result.entries:
                item = {
                    "name": entry.name,
                    "path": entry.path_display,
                    "id": entry.id
                }
                
                if isinstance(entry, FileMetadata):
                    item["type"] = "file"
                    item["size"] = entry.size
                    item["modified"] = entry.server_modified.isoformat()
                elif isinstance(entry, FolderMetadata):
                    item["type"] = "folder"
                
                items.append(item)
                
            return items
        except ApiError as e:
            raise ApiError(f"Error listing folder contents: {str(e)}", e)
    
    @staticmethod
    def search_files(dbx: dropbox.Dropbox, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for files and folders in Dropbox
        
        Args:
            dbx: Authenticated Dropbox client
            query: Search query string
            max_results: Maximum number of results (default: 10)
            
        Returns:
            List of dictionaries with file/folder details
            
        Raises:
            ApiError: If there's an issue with the API call
        """
        try:
            result = dbx.files_search_v2(query, max_results=max_results)
            items = []
            
            for match in result.matches:
                entry = match.metadata.metadata
                item = {
                    "name": entry.name,
                    "path": entry.path_display,
                    "id": entry.id
                }
                
                if isinstance(entry, FileMetadata):
                    item["type"] = "file"
                    item["size"] = entry.size
                    item["modified"] = entry.server_modified.isoformat()
                elif isinstance(entry, FolderMetadata):
                    item["type"] = "folder"
                
                items.append(item)
                
            return items
        except ApiError as e:
            raise ApiError(f"Error searching Dropbox: {str(e)}", e)
    
    @staticmethod
    def upload_file(dbx: dropbox.Dropbox, file_path: str, 
                   content: Union[bytes, BinaryIO], overwrite: bool = False) -> Dict[str, Any]:
        """
        Upload a file to Dropbox
        
        Args:
            dbx: Authenticated Dropbox client
            file_path: Destination path in Dropbox
            content: File content as bytes or file-like object
            overwrite: Whether to overwrite existing file (default: False)
            
        Returns:
            Dictionary with file details
            
        Raises:
            ApiError: If there's an issue with the API call
        """
        mode = dropbox.files.WriteMode.overwrite if overwrite else dropbox.files.WriteMode.add
        
        try:
            if isinstance(content, bytes):
                result = dbx.files_upload(content, file_path, mode=mode)
            else:
                result = dbx.files_upload(content.read(), file_path, mode=mode)
                
            return {
                "name": result.name,
                "path": result.path_display,
                "id": result.id,
                "size": result.size,
                "modified": result.server_modified.isoformat()
            }
        except ApiError as e:
            raise ApiError(f"Error uploading file: {str(e)}", e)
    
    @staticmethod
    def download_file(dbx: dropbox.Dropbox, file_path: str) -> Dict[str, Any]:
        """
        Download a file from Dropbox
        
        Args:
            dbx: Authenticated Dropbox client
            file_path: Path of the file to download
            
        Returns:
            Dictionary with file content and metadata
            
        Raises:
            ApiError: If there's an issue with the API call
        """
        try:
            metadata, response = dbx.files_download(file_path)
            content = response.content
            
            return {
                "content": content,
                "name": metadata.name,
                "path": metadata.path_display,
                "id": metadata.id,
                "size": metadata.size,
                "modified": metadata.server_modified.isoformat()
            }
        except ApiError as e:
            raise ApiError(f"Error downloading file: {str(e)}", e)
    
    @staticmethod
    def create_folder(dbx: dropbox.Dropbox, folder_path: str) -> Dict[str, Any]:
        """
        Create a folder in Dropbox
        
        Args:
            dbx: Authenticated Dropbox client
            folder_path: Path for the new folder
            
        Returns:
            Dictionary with folder details
            
        Raises:
            ApiError: If there's an issue with the API call
        """
        try:
            result = dbx.files_create_folder_v2(folder_path)
            metadata = result.metadata
            
            return {
                "name": metadata.name,
                "path": metadata.path_display,
                "id": metadata.id
            }
        except ApiError as e:
            raise ApiError(f"Error creating folder: {str(e)}", e)
    
    @staticmethod
    def delete_file(dbx: dropbox.Dropbox, file_path: str) -> Dict[str, Any]:
        """
        Delete a file or folder from Dropbox
        
        Args:
            dbx: Authenticated Dropbox client
            file_path: Path of the file/folder to delete
            
        Returns:
            Dictionary with deletion confirmation
            
        Raises:
            ApiError: If there's an issue with the API call
        """
        try:
            result = dbx.files_delete_v2(file_path)
            metadata = result.metadata
            
            return {
                "name": metadata.name,
                "path": metadata.path_display,
                "id": metadata.id,
                "status": "deleted"
            }
        except ApiError as e:
            raise ApiError(f"Error deleting file: {str(e)}", e) 