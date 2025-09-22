import requests
import logging
import mimetypes
import urllib.parse
from dify_plugin.entities.datasource import OnlineDriveFile, OnlineDriveFileBucket, OnlineDriveBrowseFilesResponse

logger = logging.getLogger(__name__)


def parse_path(prefix: str, access_token: str) -> tuple[str, str]:
    """
    Parse path to determine resource_id and item_id

    Args:
        prefix: Path prefix, format as "resource_id" or "resource_id/path/to/folder"
        access_token: Access token

    Returns:
        Tuple (resource_id, item_id), where item_id may be empty
    """

    if not prefix or prefix.strip() == "":
        return "", ""  # Empty prefix means list all resources

    prefix = prefix.strip("/")
    if not prefix:
        return "", ""

    parts = prefix.split("/", 1)
    resource_id = parts[0]

    item_id = parts[1] if len(parts) > 1 else ""

    return resource_id, item_id


def list_all_resources(
    base_url: str, resource: str, headers: dict, max_keys: int, next_page_parameters: dict, bucket_name: str
) -> OnlineDriveBrowseFilesResponse:
    """
    List all resources (sites/groups)
    """
    # Build query parameters for Graph API
    params = {"$top": max_keys, "$select": "id,displayName,name,webUrl"}
    if resource == "sites":
        params["search"] = "*"

    # If pagination parameters exist, add skip parameter
    if next_page_parameters and next_page_parameters.get("skip"):
        params["$skip"] = next_page_parameters.get("skip")

    # Send HTTP request to Graph API
    url = f"{base_url}/{resource}"
    response = requests.get(url, headers=headers, params=params, timeout=30)

    # Check authentication errors
    if response.status_code == 401:
        raise ValueError(
            "Authentication failed (401 Unauthorized). Access token may have expired. "
            "Please refresh or re-authorize the connection."
        )
    elif response.status_code != 200:
        raise ValueError(f"Failed to list {resource}: {response.status_code} - {response.text[:200]}")

    # Parse response
    results = response.json()

    items = results.get("value", [])

    files = []
    for item in items:
        # Each item is treated as a folder
        name = item.get("displayName") or item.get("name", "")
        files.append(
            OnlineDriveFile(
                id=item.get("id", ""),
                name=name,
                size=0,  # Sites/Groups don't have size
                type="folder",  # Sites/Groups are folders
            )
        )

    # Handle pagination - Graph API uses skip-based pagination
    odata_next_link = results.get("@odata.nextLink")
    is_truncated = bool(odata_next_link)
    next_page_parameters = {}

    if is_truncated and odata_next_link:
        # Extract skip parameter from next link
        parsed_url = urllib.parse.urlparse(odata_next_link)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if "$skip" in query_params:
            next_page_parameters = {"skip": int(query_params["$skip"][0])}

    return OnlineDriveBrowseFilesResponse(
        result=[
            OnlineDriveFileBucket(
                bucket=bucket_name, files=files, is_truncated=is_truncated, next_page_parameters=next_page_parameters
            )
        ]
    )


def browse_drive(
    base_url: str,
    resource: str,
    resource_id: str,
    item_id: str,
    headers: dict,
    max_keys: int,
    next_page_parameters: dict,
    bucket_name: str,
) -> OnlineDriveBrowseFilesResponse:
    """
    Browse drive content of a specific resource (site/group)
    """
    # Build URL for the default drive
    if not item_id:
        # List root items in the default drive
        url = f"{base_url}/{resource}/{resource_id}/drive/root/children"
    else:
        # List items in a specific folder path
        url = f"{base_url}/{resource}/{resource_id}/drive/items/{item_id}/children"

    # Build query parameters
    params = {"$top": max_keys, "$select": "id,name,size,folder,file,lastModifiedDateTime"}

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
        raise ValueError(f"{resource.capitalize()} '{resource_id}' or path '{item_id}' not found.")
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

        files.append(
            OnlineDriveFile(
                id=f"{resource_id}/{item.get('id', '')}", name=item.get("name", ""), size=size, type=file_type
            )
        )

    # Handle pagination - Graph API uses skip-based pagination
    odata_next_link = results.get("@odata.nextLink")
    is_truncated = bool(odata_next_link)
    next_page_parameters = {}

    if is_truncated and odata_next_link:
        # Extract skip parameter from next link
        parsed_url = urllib.parse.urlparse(odata_next_link)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if "$skip" in query_params:
            next_page_parameters = {"skip": int(query_params["$skip"][0])}
    return OnlineDriveBrowseFilesResponse(
        result=[
            OnlineDriveFileBucket(
                bucket=resource_id, files=files, is_truncated=is_truncated, next_page_parameters=next_page_parameters
            )
        ]
    )


def get_mime_type_from_filename(filename: str) -> str:
    """Determine MIME type from file extension."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def download_file(base_url: str, resource: str, file_id: str, headers: dict, get_mime_type_from_filename):
    try:
        # For SharePoint, we need to determine if this is a direct drive item
        # file_id may be in format "resource_id/drive_item_id" or just "drive_item_id"
        resource_id, item_id = file_id.split("/", 1)

        metadata_url = f"{base_url}/{resource}/{resource_id}/drive/items/{item_id}"
        content_url = f"{base_url}/{resource}/{resource_id}/drive/items/{item_id}/content"

        # First, get file metadata
        metadata_params = {"$select": "id,name,size,folder,file"}
        metadata_response = requests.get(metadata_url, headers=headers, params=metadata_params, timeout=30)

        if metadata_response.status_code == 401:
            logger.error(f"Authentication failed: {metadata_response.text[:200]}")
            raise ValueError(
                "Authentication failed (401 Unauthorized). Access token may have expired. "
                "Please refresh or re-authorize the connection."
            )
        elif metadata_response.status_code == 404:
            logger.error(f"File not found: {item_id}")
            raise ValueError(f"File with ID '{item_id}' not found.")
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
            stream=True,  # Stream response for large files
        )

        if content_response.status_code == 401:
            logger.error("Authentication failed during file download")
            raise ValueError(
                "Authentication failed during file download. " "Please refresh or re-authorize the connection."
            )
        elif content_response.status_code == 404:
            logger.error(f"File content not found: {item_id}")
            raise ValueError(f"File content with ID '{item_id}' not found.")
        elif content_response.status_code != 200:
            logger.error(f"Failed to download file: {content_response.status_code}")
            raise ValueError(f"Failed to download file: {content_response.status_code}")

        # Get content
        file_content = content_response.content

        # Determine MIME type from file extension or use default
        mime_type = get_mime_type_from_filename(file_name)

        return file_content, file_name, mime_type

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {e}")
        raise ValueError(f"Network error occurred while downloading file: {str(e)}") from e
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
