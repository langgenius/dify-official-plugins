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


class OneDriveDataSource(OnlineDriveDatasource):
    
    def _refresh_token_if_needed(self):
        """Refresh token and update runtime credentials"""
        import requests
        
        credentials = self.runtime.credentials
        refresh_token = credentials.get("refresh_token")
        
        if not refresh_token:
            raise ValueError("Missing refresh_token for token refresh")

        # Note: In this implementation, client_secret should be obtained from system configuration
        # For now, we'll require re-authorization when token expires
        raise ValueError("Token refresh requires system configuration access. Please re-authorize through OneDrive OAuth.")
    
    def _browse_files(
        self,  request: OnlineDriveBrowseFilesRequest
    ) -> OnlineDriveBrowseFilesResponse:
        credentials = self.runtime.credentials
        bucket_name = (request.bucket or "onedrive")
        prefix = request.prefix or "root"
        max_keys = request.max_keys or 5
        next_page_parameters = request.next_page_parameters or {}

        access_token = credentials.get("access_token") if credentials else None
        if not access_token:
            raise ValueError("Credentials not found")

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        base_url = "https://graph.microsoft.com/v1.0/me/drive"
        url = f"{base_url}/root/children" if prefix == "root" else f"{base_url}/items/{prefix}/children"
        params = {"$top": max_keys}
        if next_page_parameters and next_page_parameters.get("next_link"):
            url = next_page_parameters["next_link"]
            params = {}

        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 401:
            # Token may have expired, try to refresh
            try:
                updated_credentials = self._refresh_token_if_needed()
                headers["Authorization"] = f"Bearer {updated_credentials['access_token']}"
                resp = requests.get(url, headers=headers, params=params, timeout=10)
            except Exception as e:
                raise ValueError(f"Token refresh failed: {str(e)}")
        
        if resp.status_code >= 400:
            raise ValueError(f"Microsoft Graph list error: {resp.status_code} {resp.text}")
        data = resp.json() if resp.content else {}
        items = data.get("value", [])

        files = []
        for item in items:
            is_folder = bool(item.get("folder"))
            size_raw = item.get("size", 0)
            try:
                size = 0 if is_folder else int(size_raw)
            except Exception:
                size = 0
            files.append(OnlineDriveFile(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                size=size,
                type="folder" if is_folder else "file",
            ))

        next_link = data.get("@odata.nextLink") or ""
        next_page_parameters = {"next_link": next_link} if next_link else {}
        is_truncated = bool(next_link)
        return OnlineDriveBrowseFilesResponse(result=[OnlineDriveFileBucket(bucket=bucket_name, files=files, is_truncated=is_truncated, next_page_parameters=next_page_parameters)])

    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        credentials = self.runtime.credentials
        file_id = request.id

        access_token = credentials.get("access_token") if credentials else None
        if not access_token:
            raise ValueError("Credentials not found")

        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        base_url = "https://graph.microsoft.com/v1.0/me/drive/items"

        meta_resp = requests.get(f"{base_url}/{file_id}", headers=headers, timeout=10)
        meta = meta_resp.json() if meta_resp.content else {}

        content_resp = requests.get(f"{base_url}/{file_id}/content", headers=headers, timeout=30)
        if content_resp.status_code == 401:
            # Token may have expired, try to refresh
            try:
                updated_credentials = self._refresh_token_if_needed()
                headers["Authorization"] = f"Bearer {updated_credentials['access_token']}"
                content_resp = requests.get(f"{base_url}/{file_id}/content", headers=headers, timeout=30)
            except Exception as e:
                raise ValueError(f"Token refresh failed: {str(e)}")
        
        content_resp.raise_for_status()
        file_bytes = content_resp.content

        yield self.create_blob_message(file_bytes, meta={
            "file_name": meta.get("name"),
            "mime_type": meta.get("file", {}).get("mimeType", "application/octet-stream"),
        })

