from collections.abc import Generator
from typing import Dict, List, Optional, Any
import mimetypes
import os
import logging
from datetime import datetime
import requests
from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.core.exceptions import AzureError, ResourceNotFoundError

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from dify_plugin.entities.datasource import (
    DatasourceMessage,
    OnlineDriveBrowseFilesRequest,
    OnlineDriveBrowseFilesResponse,
    OnlineDriveDownloadFileRequest,
    OnlineDriveFile,
    OnlineDriveFileBucket,
)
from dify_plugin.interfaces.datasource.online_drive import OnlineDriveDatasource


class AzureBlobDataSource(OnlineDriveDatasource):
    
    def invoke(self, request: Any) -> Generator[DatasourceMessage, None, None]:
        """Only use OnlineDrive standard browse/download process."""
        yield from super().invoke(request)

    def _get_blob_service_client(self) -> BlobServiceClient:
        """Get Blob service client"""
        if not hasattr(self, '_blob_service_client') or self._blob_service_client is None:
            credentials = self.runtime.credentials
            auth_method = credentials.get("auth_method", "account_key")
            account_name = credentials.get("account_name")
            endpoint_suffix = credentials.get("endpoint_suffix", "core.windows.net")
            
            if auth_method == "account_key":
                account_key = credentials.get("account_key")
                account_url = f"https://{account_name}.blob.{endpoint_suffix}"
                self._blob_service_client = BlobServiceClient(
                    account_url=account_url, 
                    credential=account_key
                )
                
            elif auth_method == "sas_token":
                sas_token = credentials.get("sas_token")
                if not sas_token.startswith('?'):
                    sas_token = '?' + sas_token
                account_url = f"https://{account_name}.blob.{endpoint_suffix}"
                self._blob_service_client = BlobServiceClient(
                    account_url=account_url + sas_token
                )
                
            elif auth_method == "connection_string":
                connection_string = credentials.get("connection_string")
                self._blob_service_client = BlobServiceClient.from_connection_string(
                    connection_string
                )
                
            elif auth_method == "oauth":
                access_token = credentials.get("access_token")
                account_url = f"https://{account_name}.blob.{endpoint_suffix}"
                
                # Create simple token credential
                from azure.core.credentials import AccessToken
                from datetime import datetime, timezone
                
                class SimpleTokenCredential:
                    def __init__(self, token, expires_in=3600):
                        self.token = token
                        self.expires_at = int(datetime.now(timezone.utc).timestamp()) + expires_in
                    
                    def get_token(self, *scopes, **kwargs):
                        current_time = int(datetime.now(timezone.utc).timestamp())
                        if current_time >= self.expires_at - 300:  # Refresh 5 minutes early
                            from azure.core.exceptions import ClientAuthenticationError
                            raise ClientAuthenticationError("Access token has expired, refresh required")
                        return AccessToken(self.token, self.expires_at)
                
                credential = SimpleTokenCredential(access_token)
                self._blob_service_client = BlobServiceClient(
                    account_url=account_url, 
                    credential=credential
                )
                
            else:
                raise ValueError(f"Unsupported authentication method: {auth_method}")
                
        return self._blob_service_client
    
    def _browse_files(self, request: OnlineDriveBrowseFilesRequest) -> OnlineDriveBrowseFilesResponse:
        """Browse Azure Blob Storage files"""
        bucket_name = request.bucket  # Container name
        prefix = request.prefix or ""  # Blob prefix
        max_keys = request.max_keys or 100
        next_page_parameters = request.next_page_parameters or {}
        
        # Fix: If bucket_name is empty but prefix contains container path, parse from prefix
        if not bucket_name and prefix:
            # Check if prefix contains container name (format like "container-name/" or "container-name/path/")
            prefix_parts = prefix.strip('/').split('/')
            if len(prefix_parts) >= 1:
                # First part might be container name
                potential_container = prefix_parts[0]
                remaining_prefix = '/'.join(prefix_parts[1:]) if len(prefix_parts) > 1 else ""
                
                # Try to verify if this is a valid container name
                blob_service_client = self._get_blob_service_client()
                try:
                    container_client = blob_service_client.get_container_client(potential_container)
                    # Simple check if container exists (no exception means container exists)
                    container_client.get_container_properties()
                    
                    # Container exists, use parsed values
                    bucket_name = potential_container
                    prefix = remaining_prefix
                except Exception:
                    # Parsing failed, continue with original values
                    pass
        
        try:
            blob_service_client = self._get_blob_service_client()
            
            if not bucket_name:
                # List all containers
                return self._list_containers(blob_service_client, max_keys, next_page_parameters)
            else:
                # List blobs in specified container
                return self._list_blobs_in_container(
                    blob_service_client, bucket_name, prefix, max_keys, next_page_parameters
                )
                
        except ResourceNotFoundError:
            if bucket_name:
                raise ValueError(f"Container '{bucket_name}' not found")
            else:
                raise ValueError("Storage account not accessible")
        except AzureError as e:
            raise ValueError(f"Azure Blob Storage error: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to browse Azure Blob Storage: {str(e)}")
    
    def _list_containers(self, blob_service_client: BlobServiceClient, max_keys: int, 
                        next_page_parameters: Dict) -> OnlineDriveBrowseFilesResponse:
        """List all containers"""
        continuation_token = next_page_parameters.get("continuation_token")
        
        # According to Azure Blob SDK documentation, list_containers doesn't support results_per_page parameter
        # Use pagination iterator to control page size
        if continuation_token:
            containers_page = blob_service_client.list_containers().by_page(
                continuation_token=continuation_token
            )
        else:
            containers_page = blob_service_client.list_containers().by_page()
        
        page = next(containers_page)
        
        files = []
        for container in page:
            # Get container properties
            try:
                container_client = blob_service_client.get_container_client(container.name)
                container_properties = container_client.get_container_properties()
                
                files.append(OnlineDriveFile(
                    id=container.name,
                    name=container.name,
                    size=0,  # Container itself has no size
                    type="folder",
                    metadata={
                        "container_name": container.name,
                        "last_modified": container.last_modified.isoformat() if container.last_modified else "",
                        "etag": container.etag or "",
                        "public_access": getattr(container_properties, "public_access", "none"),
                        "has_immutability_policy": getattr(container_properties, "has_immutability_policy", False),
                        "has_legal_hold": getattr(container_properties, "has_legal_hold", False)
                    }
                ))
            except Exception:
                # If unable to get container properties, use basic info
                files.append(OnlineDriveFile(
                    id=container.name,
                    name=container.name,
                    size=0,
                    type="folder",
                    metadata={
                        "container_name": container.name,
                        "last_modified": container.last_modified.isoformat() if container.last_modified else "",
                        "etag": container.etag or ""
                    }
                ))
        
        # Check if there are more pages
        new_continuation_token = getattr(page, 'continuation_token', None)
        is_truncated = new_continuation_token is not None
        next_page_params = {"continuation_token": new_continuation_token} if is_truncated else {}
        
        return OnlineDriveBrowseFilesResponse(
            result=[OnlineDriveFileBucket(
                bucket="",  # bucket is empty when listing containers
                files=files,
                is_truncated=is_truncated,
                next_page_parameters=next_page_params
            )]
        )
    
    def _list_blobs_in_container(self, blob_service_client: BlobServiceClient, container_name: str,
                               prefix: str, max_keys: int, next_page_parameters: Dict) -> OnlineDriveBrowseFilesResponse:
        """List blobs in container"""
        continuation_token = next_page_parameters.get("continuation_token")
        
        try:
            container_client = blob_service_client.get_container_client(container_name)
            items_iter = container_client.walk_blobs(
                name_starts_with=prefix if prefix else None
            )

            # Pagination
            items_page_iter = items_iter.by_page(continuation_token) if continuation_token else items_iter.by_page()
            page = next(items_page_iter)

            files = []
            seen_dirs = set()

            # BlobPrefix represents directory, BlobProperties represents file
            for item in page:
                item_name = getattr(item, "name", None)
                if not item_name:
                    continue

                # Calculate relative name for display
                display_name = item_name[len(prefix):] if prefix and item_name.startswith(prefix) else item_name

                # Fix folder judgment logic: only explicit directory markers are folders
                is_folder = (item_name.endswith("/") and getattr(item, "size", 0) == 0) or type(item).__name__ == "BlobPrefix"
                
                if is_folder:
                    # Directory: only show first-level directories in current layer
                    first_dir = display_name.rstrip("/")
                    if "/" in first_dir:
                        first_dir = first_dir.split("/", 1)[0]
                    
                    if first_dir and first_dir not in seen_dirs:
                        seen_dirs.add(first_dir)
                        dir_path = f"{prefix}{first_dir}/" if prefix else f"{first_dir}/"
                        # Construct correct directory ID format: container_name/dir_path
                        dir_id = f"{container_name}/{dir_path}"
                        files.append(OnlineDriveFile(
                            id=dir_id,  # Use container_name/dir_path format
                            name=first_dir,
                            size=0,
                            type="folder",
                            metadata={
                                "container_name": container_name,
                                "blob_path": dir_path,
                                "is_directory": True
                            }
                        ))
                else:
                    # File: only show current level (no further /)
                    if "/" in display_name:
                        # Deeper level files not shown in this layer, carried by directory items
                        continue
                    
                    content_type = self._get_content_type(item_name, getattr(item, "content_settings", None))
                    size_val = getattr(item, "size", 0) or 0
                    last_modified = getattr(item, "last_modified", None)
                    etag = getattr(item, "etag", "") or ""
                    creation_time = getattr(item, "creation_time", None)
                    blob_tier = getattr(item, "blob_tier", "Unknown")
                    metadata_val = getattr(item, "metadata", None) or {}

                    # Construct correct file ID format: container_name/blob_path
                    file_id = f"{container_name}/{item_name}"
                    files.append(OnlineDriveFile(
                        id=file_id,  # Use container_name/blob_path format
                        name=display_name,
                        size=size_val,
                        type="file",
                        metadata={
                            "container_name": container_name,
                            "blob_path": item_name,
                            "content_type": content_type,
                            "last_modified": last_modified.isoformat() if last_modified else "",
                            "etag": etag,
                            "blob_tier": blob_tier,
                            "creation_time": creation_time.isoformat() if creation_time else "",
                            "server_encrypted": getattr(item, "server_encrypted", False),
                            "metadata": metadata_val,
                        }
                    ))
            # Check if there are more pages
            new_continuation_token = getattr(page, 'continuation_token', None)
            is_truncated = new_continuation_token is not None
            next_page_params = {"continuation_token": new_continuation_token} if is_truncated else {}
            
            return OnlineDriveBrowseFilesResponse(
                result=[OnlineDriveFileBucket(
                    bucket=container_name,
                    files=files,
                    is_truncated=is_truncated,
                    next_page_parameters=next_page_params
                )]
            )
            
        except ResourceNotFoundError:
            raise ValueError(f"Container '{container_name}' not found")
        except AzureError as e:
            raise ValueError(f"Failed to list blobs in container '{container_name}': {str(e)}")
    
    def _get_content_type(self, blob_name: str, content_settings) -> str:
        """Get content type"""
        if content_settings and content_settings.content_type:
            return content_settings.content_type
        
        # Infer MIME type based on file extension
        mime_type, _ = mimetypes.guess_type(blob_name)
        return mime_type or "application/octet-stream"
    
    def _download_file(self, request: OnlineDriveDownloadFileRequest) -> Generator[DatasourceMessage, None, None]:
        """Download file content"""
        file_id = request.id  # Format: container_name/blob_path
        
        if '/' not in file_id:
            raise ValueError("Invalid file ID format. Expected: container_name/blob_path")
        
        parts = file_id.split('/', 1)
        container_name = parts[0]
        blob_path = parts[1]
        
        try:
            logger.info(f"[Azure Blob] Starting download process for file: {file_id}")
            blob_service_client = self._get_blob_service_client()
            blob_client = blob_service_client.get_blob_client(
                container=container_name, 
                blob=blob_path
            )
            
            # Get Blob properties
            blob_properties = blob_client.get_blob_properties()
            logger.info(f"[Azure Blob] Blob properties retrieved: size={blob_properties.size}, container={container_name}")
            
            # Check Blob tier, special handling needed for archive tier
            blob_tier = getattr(blob_properties, 'blob_tier', '')
            if blob_tier and blob_tier.lower() == 'archive':
                logger.error(f"[Azure Blob] Blob is in archive tier: {blob_path}")
                raise ValueError(f"Blob '{blob_path}' is in Archive tier and needs to be rehydrated before download")
            
            # Verify file exists and is valid
            blob_size = blob_properties.size
            if blob_size is None or blob_size < 0:
                raise ValueError(f"Invalid blob size: {blob_size}")
            
            content_type = self._get_content_type(blob_path, blob_properties.content_settings)
            logger.info(f"[Azure Blob] Blob metadata: size={blob_size}, type={content_type}, tier={blob_tier}")
            
            # Prefer SAS direct HTTP download (avoid SDK limitations)
            credentials = self.runtime.credentials
            auth_method = (credentials or {}).get("auth_method", "account_key")
            if auth_method == "sas_token":
                logger.info("[Azure Blob] Using SAS HTTP download path")
                yield from self._download_via_sas_http(container_name, blob_path)
            else:
                # For large files, use streaming download (SDK)
                if blob_size > 50 * 1024 * 1024:  # 50MB
                    logger.info(f"[Azure Blob] Using large file download for {blob_size} bytes")
                    yield from self._download_large_blob(blob_client, blob_path, content_type, blob_size)
                else:
                    logger.info(f"[Azure Blob] Using small file download for {blob_size} bytes")
                    yield from self._download_small_blob(blob_client, blob_path, content_type, blob_size)
                
            logger.info(f"[Azure Blob] Download process completed successfully for: {file_id}")
                
        except ResourceNotFoundError:
            logger.error(f"[Azure Blob] Blob not found: {blob_path} in container {container_name}")
            raise ValueError(f"Blob '{blob_path}' not found in container '{container_name}'")
        except AzureError as e:
            logger.error(f"[Azure Blob] Azure error during download: {str(e)}")
            raise ValueError(f"Failed to download blob '{blob_path}': {str(e)}")
        except Exception as e:
            logger.error(f"[Azure Blob] Unexpected error during download: {str(e)}")
            raise ValueError(f"Error downloading file: {str(e)}")

    def _download_via_sas_http(self, container_name: str, blob_path: str) -> Generator[DatasourceMessage, None, None]:
        """Download via HTTP using SAS URL (not dependent on SDK data stream)."""
        credentials = self.runtime.credentials or {}
        account = credentials.get("account_name")
        suffix = credentials.get("endpoint_suffix", "core.windows.net")
        sas = credentials.get("sas_token") or ""
        if not account:
            raise ValueError("account_name not configured")
        if not sas:
            raise ValueError("sas_token not configured for SAS HTTP download")
        if not sas.startswith("?"):
            sas = "?" + sas
        url = f"https://{account}.blob.{suffix}/{container_name}/{blob_path}{sas}"

        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            file_name = os.path.basename(blob_path)
            content_length_header = resp.headers.get("Content-Length")
            try:
                content_length = int(content_length_header) if content_length_header else 0
            except Exception:
                content_length = 0

            # Small files return at once
            if 0 < content_length <= 50 * 1024 * 1024:
                data = resp.content
                yield self.create_blob_message(data, meta={
                    "file_name": file_name,
                    "mime_type": content_type,
                    "size": len(data),
                })
                return

            # Large files return in chunks
            chunk_size = 8 * 1024 * 1024
            buffer = bytearray()
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                buffer.extend(chunk)
                if len(buffer) >= 100 * 1024 * 1024:  # 100MB batch output
                    yield self.create_blob_message(bytes(buffer), meta={
                        "file_name": file_name,
                        "mime_type": content_type,
                        "is_partial": True,
                    })
                    buffer = bytearray()

            if buffer:
                yield self.create_blob_message(bytes(buffer), meta={
                    "file_name": file_name,
                    "mime_type": content_type,
                    "is_partial": False,
                })
    
    def _download_small_blob(self, blob_client, blob_path: str, content_type: str, 
                           blob_size: int) -> Generator[DatasourceMessage, None, None]:
        """Download small file"""
        try:
            logger.info(f"[Azure Blob] Starting download of small file: {blob_path}")
            download_stream = blob_client.download_blob()
            content = download_stream.readall()
            
            # Verify download success
            actual_size = len(content)
            if actual_size != blob_size:
                logger.warning(f"[Azure Blob] Size mismatch for {blob_path}: expected {blob_size}, got {actual_size}")
            else:
                logger.info(f"[Azure Blob] Successfully downloaded {blob_path}: {actual_size} bytes")
            
            # Verify content is not empty
            if not content:
                raise ValueError(f"Downloaded content is empty for blob: {blob_path}")
            
            # Extract file name and MIME type
            file_name = os.path.basename(blob_path)
            
            logger.info(f"[Azure Blob] Creating blob message for {file_name} with {actual_size} bytes")
            yield self.create_blob_message(
                blob=content,
                meta={
                    "file_name": file_name,
                    "mime_type": content_type,
                    "size": actual_size,
                    "download_success": True
                }
            )
            logger.info(f"[Azure Blob] Successfully yielded blob message for {file_name}")
            
        except Exception as e:
            raise ValueError(f"Failed to download blob content: {str(e)}")
    
    def _download_large_blob(self, blob_client, blob_path: str, content_type: str,
                           blob_size: int) -> Generator[DatasourceMessage, None, None]:
        """Download large file in chunks"""
        try:
            logger.info(f"[Azure Blob] Starting download of large file: {blob_path} ({blob_size} bytes)")
            # Extract file name
            file_name = os.path.basename(blob_path)
            
            chunk_size = 8 * 1024 * 1024  # 8MB chunks
            downloaded_content = bytearray()
            total_downloaded = 0
            
            # Download in chunks
            for i in range(0, blob_size, chunk_size):
                end_range = min(i + chunk_size - 1, blob_size - 1)
                
                download_stream = blob_client.download_blob(offset=i, length=end_range - i + 1)
                chunk = download_stream.readall()
                downloaded_content.extend(chunk)
                total_downloaded += len(chunk)
                
                logger.debug(f"[Azure Blob] Downloaded chunk {i//chunk_size + 1}: {len(chunk)} bytes (total: {total_downloaded}/{blob_size})")
                
                # If accumulated content is too large, can yield in batches
                if len(downloaded_content) > 100 * 1024 * 1024:  # 100MB
                    yield self.create_blob_message(
                        blob=bytes(downloaded_content),
                        meta={
                            "file_name": file_name,
                            "mime_type": content_type,
                            "size": len(downloaded_content),
                            "is_partial": True
                        }
                    )
                    downloaded_content = bytearray()
            
            # Verify download integrity
            if total_downloaded != blob_size:
                logger.error(f"[Azure Blob] Download incomplete: expected {blob_size}, got {total_downloaded}")
                raise ValueError(f"Download incomplete: expected {blob_size}, got {total_downloaded}")
            
            logger.info(f"[Azure Blob] Large file download completed: {total_downloaded} bytes")
            
            # Output remaining content
            if downloaded_content:
                yield self.create_blob_message(
                    blob=bytes(downloaded_content),
                    meta={
                        "file_name": file_name,
                        "mime_type": content_type,
                        "size": len(downloaded_content),
                        "download_success": True,
                        "is_partial": False
                    }
                )
                
        except Exception as e:
            raise ValueError(f"Failed to download large blob: {str(e)}")
