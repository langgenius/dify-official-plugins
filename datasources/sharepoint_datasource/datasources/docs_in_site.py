import logging
from collections.abc import Generator
import requests

from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource

from .utils import graph_utils

logger = logging.getLogger(__name__)


class SharePointDataSource(OnlineDriveDatasource):
    _BASE_URL = "https://graph.microsoft.com/v1.0"
    _RESOURCE = "sites"

    def _browse_files(self, request: OnlineDriveBrowseFilesRequest) -> OnlineDriveBrowseFilesResponse:
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
        site_id, item_id = self._parse_path(prefix, access_token)

        # Prepare headers for HTTP requests
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

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

    def _parse_path(self, prefix: str, access_token: str) -> tuple[str, str]:
        return graph_utils.parse_path(prefix, access_token)

    def _list_all_sites(
        self, headers: dict, max_keys: int, next_page_parameters: dict, bucket_name: str
    ) -> OnlineDriveBrowseFilesResponse:
        return graph_utils.list_all_resources(
            self._BASE_URL, self._RESOURCE, headers, max_keys, next_page_parameters, bucket_name
        )

    def _browse_site_drive(
        self, site_id: str, item_id: str, headers: dict, max_keys: int, next_page_parameters: dict, bucket_name: str
    ) -> OnlineDriveBrowseFilesResponse:
        return graph_utils.browse_drive(
            self._BASE_URL, self._RESOURCE, site_id, item_id, headers, max_keys, next_page_parameters, bucket_name
        )

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        file_id = request.id

        if not credentials:
            raise ValueError("No credentials found")

        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")

        # Prepare headers for HTTP requests
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        try:
            file_content, file_name, mime_type = graph_utils.download_file(
                self._BASE_URL, self._RESOURCE, file_id, headers, self._get_mime_type_from_filename
            )
            yield self.create_blob_message(file_content, meta={"file_name": file_name, "mime_type": mime_type})
        except Exception as e:
            raise

    def _get_mime_type_from_filename(self, filename: str) -> str:
        return graph_utils.get_mime_type_from_filename(filename)
