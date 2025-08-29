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


class SharePointDataSource(OnlineDriveDatasource):
    _BASE_URL = "https://graph.microsoft.com/v1.0"
    
    def _get_site_id_by_name(self, site_name: str, access_token: str) -> str:
        """
        Get site ID by site name

        Args:
            site_name: Site name
            access_token: Access token

        Returns:
            Site ID

        Raises:
            ValueError: If site not found or API call fails
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        url = f"{self._BASE_URL}/sites"
        params = {
            "search": site_name,
            "$select": "id,name,webUrl,displayName"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 401:
                raise ValueError(
                    "Authentication failed (401 Unauthorized). Access token may have expired. "
                    "Please refresh or re-authorize the connection."
                )
            elif response.status_code != 200:
                raise ValueError(f"Failed to search for site '{site_name}': {response.status_code} - {response.text[:200]}")

            results = response.json()
            sites = results.get("value", [])

            if not sites:
                raise ValueError(f"No site found with name '{site_name}'")

            # Return the first matching site ID
            site_id = sites[0].get("id")
            if not site_id:
                raise ValueError(f"Site ID not found for site '{site_name}'")

            return site_id

        except requests.exceptions.RequestException as e:
            raise ValueError(f"Network error occurred while searching for site '{site_name}': {str(e)}") from e

    def _parse_sharepoint_path(self, prefix: str, access_token: str) -> tuple[str, str]:
        """
        Parse SharePoint path to determine site_id and item_id

        Args:
            prefix: Path prefix, format as "site_name" or "site_name/path/to/folder"
            access_token: Access token

        Returns:
            Tuple (site_id, item_id), where item_id may be empty
        """
        if not prefix or prefix.strip() == "":
            return "", ""  # Empty prefix means list all sites
            
        prefix = prefix.strip("/")
        if not prefix:
            return "", ""
            
        parts = prefix.split("/", 1)
        site_id = parts[0]

        # # Use new method to get site ID by name
        # site_id = self._get_site_id_by_name(site_name, access_token)
        
        item_id = parts[1] if len(parts) > 1 else ""
        
        return site_id, item_id
    
    def _browse_files(
        self, request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = request.bucket
        prefix = request.prefix or ""  # Allow empty prefix for listing all sites
        max_keys = request.max_keys or 10
        next_page_parameters = request.next_page_parameters or {}

        if not credentials:
            raise ValueError("No credentials found")

        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")

        # Parse prefix to determine site_id and item_id
        site_id, item_id = self._parse_sharepoint_path(prefix, access_token)

        # Prepare headers for HTTP requests
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }

        try:
            if not site_id:
                # Empty prefix: Use Graph API /sites to list all sites
                return self._list_all_sites(headers, max_keys, next_page_parameters, bucket_name)
            else:
                # Non-empty prefix: Browse specific site's drive content
                return self._browse_site_drive(site_id, item_id, headers, max_keys, next_page_parameters, bucket_name)
                
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Network error occurred while accessing SharePoint: {str(e)}") from e
        except Exception as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                raise ValueError(
                    "Authentication failed. Access token may have expired. "
                    "Please refresh or re-authorize the connection."
                ) from e
            raise
    
    def _list_all_sites(self, headers: dict, max_keys: int, next_page_parameters: dict, bucket_name: str) -> OnlineDriveBrowseFilesResponse:
        """
        List all SharePoint sites
        """
        # Build query parameters for Graph API
        params = {
            "$top": max_keys,
            "$select": "id,name,webUrl,displayName",
            "search": "*"
        }

        # If pagination parameters exist, add skip parameter
        if next_page_parameters and next_page_parameters.get("skip"):
            params["$skip"] = next_page_parameters.get("skip")

        # Send HTTP request to Graph API /sites
        url = f"{self._BASE_URL}/sites"
        response = requests.get(url, headers=headers, params=params, timeout=30)

        # Check authentication errors
        if response.status_code == 401:
            raise ValueError(
                "Authentication failed (401 Unauthorized). Access token may have expired. "
                "Please refresh or re-authorize the connection."
            )
        elif response.status_code != 200:
            raise ValueError(f"Failed to list sites: {response.status_code} - {response.text[:200]}")

        # Parse response
        results = response.json()

        sites = results.get("value", [])

        files = []
        for site in sites:
            # Each site is treated as a folder
            site_name = site.get("displayName") or site.get("name", "")
            files.append(OnlineDriveFile(
                id=site.get("id", ""),
                name=site_name,
                size=0,  # Sites don't have size
                type="folder"  # Sites are folders
            ))

        # Handle pagination - Graph API uses skip-based pagination
        odata_next_link = results.get("@odata.nextLink")
        is_truncated = bool(odata_next_link)
        next_page_parameters = {}

        if is_truncated and odata_next_link:
            # Extract skip parameter from next link
            import urllib.parse
            parsed_url = urllib.parse.urlparse(odata_next_link)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if "$skip" in query_params:
                next_page_parameters = {"skip": int(query_params["$skip"][0])}
        
        return OnlineDriveBrowseFilesResponse(result=[
            OnlineDriveFileBucket(
                bucket=bucket_name,
                files=files, 
                is_truncated=is_truncated, 
                next_page_parameters=next_page_parameters
            )
        ])
    
    def _browse_site_drive(self, site_id: str, item_id: str, headers: dict, max_keys: int, next_page_parameters: dict, bucket_name: str) -> OnlineDriveBrowseFilesResponse:
        """
        Browse document library content of a specific site
        """

        # Build URL for the site's default drive
        if not item_id:
            # List root items in the site's default drive
            url = f"{self._BASE_URL}/sites/{site_id}/drive/root/children"
        else:
            # List items in a specific folder path
            url = f"{self._BASE_URL}/sites/{site_id}/drive/items/{item_id}/children"

        # Build query parameters
        params = {
            "$top": max_keys,
            "$select": "id,name,size,folder,file,lastModifiedDateTime"
        }

        # If pagination parameters exist, add skip parameter
        if next_page_parameters and next_page_parameters.get("skip"):
            params["$skip"] = next_page_parameters.get("skip")
        
        response = requests.get(url, headers=headers, params=params, timeout=30)

        # Check authentication errors
        if response.status_code == 401:
            raise ValueError(
                "Authentication failed (401 Unauthorized). Access token may have expired. "
                "Please refresh or re-authorize the connection."
            )
        elif response.status_code == 404:
            raise ValueError(f"Site '{site_id}' or path '{item_id}' not found.")
        elif response.status_code != 200:
            raise ValueError(f"Failed to list drive items: {response.status_code} - {response.text[:200]}")

        # Parse response
        results = response.json()
        items = results.get("value", [])

        files = []
        for item in items:
            # Check if it's a folder (has 'folder' facet)
            is_folder = "folder" in item
            file_type = "folder" if is_folder else "file"
            size = 0 if is_folder else int(item.get("size", 0))

            files.append(OnlineDriveFile(
                id=f"{site_id}/{item.get('id', '')}",
                name=item.get("name", ""),
                size=size,
                type=file_type
            ))

        # Handle pagination - Graph API uses skip-based pagination
        odata_next_link = results.get("@odata.nextLink")
        is_truncated = bool(odata_next_link)
        next_page_parameters = {}

        if is_truncated and odata_next_link:
            # Extract skip parameter from next link
            import urllib.parse
            parsed_url = urllib.parse.urlparse(odata_next_link)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if "$skip" in query_params:
                next_page_parameters = {"skip": int(query_params["$skip"][0])}

        return OnlineDriveBrowseFilesResponse(result=[
            OnlineDriveFileBucket(
                bucket=site_id, 
                files=files, 
                is_truncated=is_truncated, 
                next_page_parameters=next_page_parameters
            )
        ])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        file_id = request.id

        if not credentials:
            raise ValueError("No credentials found")

        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")

        # Prepare headers for HTTP requests
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }

        try:
            # For SharePoint, we need to determine if this is a direct drive item
            # file_id may be in format "site_name/drive_item_id" or just "drive_item_id"
            site_id, file_id = file_id.split("/", 1)

            metadata_url = f"{self._BASE_URL}/sites/{site_id}/drive/items/{file_id}"
            content_url = f"{self._BASE_URL}/sites/{site_id}/drive/items/{file_id}/content"

            # First, get file metadata
            metadata_params = {"$select": "id,name,size,folder,file"}

            metadata_response = requests.get(
                metadata_url,
                headers=headers,
                params=metadata_params,
                timeout=30
            )

            if metadata_response.status_code == 401:
                logger.error(f"Authentication failed: {metadata_response.text[:200]}")
                raise ValueError(
                    "Authentication failed (401 Unauthorized). Access token may have expired. "
                    "Please refresh or re-authorize the connection."
                )
            elif metadata_response.status_code == 404:
                logger.error(f"File not found: {file_id}")
                raise ValueError(f"File with ID '{file_id}' not found.")
            elif metadata_response.status_code != 200:
                logger.error(f"Failed to get file metadata: {metadata_response.status_code}")
                raise ValueError(f"Failed to get file metadata: {metadata_response.status_code}")

            file_metadata = metadata_response.json()
            file_name = file_metadata.get("name", "unknown")

            # Check if it's a folder (has 'folder' facet in SharePoint)
            if "folder" in file_metadata:
                raise ValueError(f"Cannot download folder '{file_name}'. Please select a file.")

            # Use SharePoint Graph API to download file content
            content_response = requests.get(
                content_url,
                headers=headers,
                timeout=60,  # Use longer timeout for file downloads
                stream=True  # Stream response for large files
            )

            if content_response.status_code == 401:
                logger.error("Authentication failed during file download")
                raise ValueError(
                    "Authentication failed during file download. "
                    "Please refresh or re-authorize the connection."
                )
            elif content_response.status_code == 404:
                logger.error(f"File content not found: {file_id}")
                raise ValueError(f"File content with ID '{file_id}' not found.")
            elif content_response.status_code != 200:
                logger.error(f"Failed to download file: {content_response.status_code}")
                raise ValueError(f"Failed to download file: {content_response.status_code}")

            # Get content
            file_content = content_response.content

            # Determine MIME type from file extension or use default
            mime_type = self._get_mime_type_from_filename(file_name)

            yield self.create_blob_message(file_content, meta={
                "file_name": file_name,
                "mime_type": mime_type
            })
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            raise ValueError(f"Network error occurred while downloading file: {str(e)}") from e
        except Exception as e:
            if "already" not in str(e).lower():  # Avoid re-raising our own errors
                logger.error(f"Unexpected error: {e}")
            raise

    def _get_mime_type_from_filename(self, filename: str) -> str:
        """Determine MIME type from file extension."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"