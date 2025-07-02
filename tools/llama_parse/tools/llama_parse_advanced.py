import logging
import os
import time
from collections.abc import Generator
from typing import Any, Optional

import nest_asyncio
import httpx
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from llama_cloud_services import LlamaParse
from llama_cloud_services.parse.utils import ResultType
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AdvancedToolParameters(BaseModel):
    files: list[File]
    result_type: ResultType
    num_workers: int
    verbose: bool
    language: str
    target_pages: Optional[str] = None
    max_pages: Optional[int] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None


mime_type_map = {
    ResultType.JSON: "application/json",
    ResultType.MD: "text/markdown",
    ResultType.TXT: "text/plain",
}


class LlamaParseAdvancedTool(Tool):
    """
    An advanced tool for parsing text using Llama Cloud Services with LLM mode
    Features include target pages, max pages, system prompt, and user prompt
    Enhanced for handling large files (50MB+) with streaming downloads
    """

    def _get_file_content_with_timeout(self, file: File, timeout: float = 300.0) -> bytes:
        """
        Get file content with enhanced timeout and streaming for large files
        """
        try:
            # Check if FILES_URL is configured (only for non-http URLs)
            if not file.url.startswith(('http://', 'https://')):
                files_url = os.getenv('FILES_URL')
                if not files_url:
                    raise ValueError(
                        f"File URL '{file.url}' is missing protocol. "
                        "Please configure the FILES_URL environment variable in your Dify .env file:\n"
                        "- For Docker Compose: FILES_URL=http://api:5001\n"
                        "- For other deployments: FILES_URL=http://YOUR_DIFY_HOST_IP:5001"
                    )
            
            # Enhanced timeout calculation for large files
            file_size_mb = getattr(file, 'size', 0) / (1024 * 1024)
            
            # More aggressive timeout for large files:
            # - Base timeout: 300 seconds (5 minutes)
            # - Small files (< 10MB): 30 seconds per MB
            # - Large files (>= 10MB): 15 seconds per MB + 60 seconds base
            if file_size_mb < 10:
                calculated_timeout = max(timeout, file_size_mb * 30)
            else:
                calculated_timeout = max(timeout, (file_size_mb * 15) + 60)
            
            # Cap timeout at 30 minutes for extremely large files
            calculated_timeout = min(calculated_timeout, 1800)
            
            logger.info(f"Downloading file '{file.filename}' ({file_size_mb:.1f}MB) with {calculated_timeout}s timeout")
            
            # Use streaming for large files to avoid memory issues
            if file_size_mb > 10:
                logger.info(f"Using streaming download for large file ({file_size_mb:.1f}MB)")
                return self._download_large_file_streaming(file, calculated_timeout)
            else:
                # Use regular download for smaller files
                with httpx.Client(timeout=calculated_timeout) as client:
                    response = client.get(file.url)
                    response.raise_for_status()
                    logger.info(f"Successfully downloaded file '{file.filename}' ({len(response.content)} bytes)")
                    return response.content
                
        except httpx.ConnectTimeout:
            raise httpx.ConnectTimeout(
                f"Connection timeout while accessing file '{file.filename}'. "
                "The file might be too large or network is slow. Try again or use a smaller file."
            )
        except httpx.ReadTimeout:
            raise httpx.ReadTimeout(
                f"Read timeout while downloading file '{file.filename}'. "
                "The file is taking too long to download. Try again or use a smaller file."
            )
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"HTTP error {e.response.status_code} while accessing file '{file.filename}': {e}",
                request=e.request,
                response=e.response
            )
        except httpx.UnsupportedProtocol as e:
            raise ValueError(
                f"Invalid file URL '{file.url}': {e}. "
                "Please ensure the FILES_URL environment variable is set correctly in your Dify .env file."
            )
        except Exception as e:
            raise Exception(f"Unexpected error while accessing file '{file.filename}': {e}")

    def _download_large_file_streaming(self, file: File, timeout: float) -> bytes:
        """
        Download large files using streaming to avoid memory issues
        """
        file_size_mb = getattr(file, 'size', 0) / (1024 * 1024)
        start_time = time.time()
        
        with httpx.Client(timeout=timeout) as client:
            with client.stream("GET", file.url) as response:
                response.raise_for_status()
                
                # Read content in chunks
                chunks = []
                total_bytes = 0
                chunk_size = 1024 * 1024  # 1MB chunks
                
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    
                    # Log progress every 10MB
                    if total_bytes % (10 * 1024 * 1024) < chunk_size:
                        elapsed = time.time() - start_time
                        speed = total_bytes / (1024 * 1024) / elapsed if elapsed > 0 else 0
                        logger.info(f"Downloaded {total_bytes / (1024 * 1024):.1f}MB of {file_size_mb:.1f}MB "
                                  f"({speed:.1f} MB/s, {elapsed:.1f}s elapsed)")
                
                # Combine all chunks
                content = b''.join(chunks)
                elapsed = time.time() - start_time
                speed = total_bytes / (1024 * 1024) / elapsed if elapsed > 0 else 0
                
                logger.info(f"Successfully downloaded file '{file.filename}' "
                          f"({total_bytes} bytes, {speed:.1f} MB/s, {elapsed:.1f}s total)")
                return content

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        nest_asyncio.apply()
        if tool_parameters.get("files") is None:
            raise ValueError("File is required")
        params = AdvancedToolParameters(**tool_parameters)
        files = params.files

        # Build parser configuration with advanced features
        parser_config = {
            "api_key": self.runtime.credentials.get("llama_cloud_api_key", ""),
            "result_type": params.result_type,
            "num_workers": params.num_workers,
            "verbose": params.verbose,
            "language": params.language,
            "ignore_errors": False,
            "parse_mode": "parse_page_with_llm",  # Enable LLM mode
        }

        # Add optional advanced parameters
        if params.target_pages:
            parser_config["target_pages"] = params.target_pages
        if params.max_pages:
            parser_config["max_pages"] = params.max_pages
        if params.system_prompt:
            parser_config["system_prompt"] = params.system_prompt
        if params.user_prompt:
            parser_config["user_prompt"] = params.user_prompt

        parser = LlamaParse(**parser_config)

        for file in files:
            try:
                # Add timeout and error handling for file access
                file_size_mb = getattr(file, 'size', 0) / (1024 * 1024)
                logger.info(f"Processing file: {file.filename} ({file_size_mb:.1f}MB)")
                
                # Show warning for very large files
                if file_size_mb > 50:
                    logger.warning(f"Processing very large file ({file_size_mb:.1f}MB). This may take several minutes.")
                    yield self.create_text_message(f"Processing large file ({file_size_mb:.1f}MB). Please be patient...")
                
                # Try to access the file content with custom timeout handling
                try:
                    file_content = self._get_file_content_with_timeout(file, timeout=300.0)
                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.HTTPStatusError, ValueError) as e:
                    error_msg = str(e)
                    logger.error(error_msg)
                    yield self.create_text_message(error_msg)
                    continue
                except Exception as e:
                    error_msg = f"Unexpected error while accessing file '{file.filename}': {e}"
                    logger.error(error_msg)
                    yield self.create_text_message(error_msg)
                    continue

                # Parse the document
                logger.info(f"Parsing file '{file.filename}' with LlamaParse LLM mode...")
                documents = parser.load_data(
                    file_path=file_content,
                    extra_info={"file_name": file.filename},
                )
                
                texts = "---".join([doc.text for doc in documents])
                yield self.create_text_message(texts)
                handled_docs = [
                    {"text": doc.text, "metadata": doc.metadata} for doc in documents
                ]
                yield self.create_json_message({file.filename: handled_docs})
                yield self.create_blob_message(
                    texts.encode(),
                    meta={
                        "mime_type": mime_type_map[params.result_type],
                    },
                )
                
                logger.info(f"Successfully processed file '{file.filename}'")
                
            except Exception as e:
                error_msg = f"Error processing file '{file.filename}': {e}"
                logger.error(error_msg)
                yield self.create_text_message(error_msg) 