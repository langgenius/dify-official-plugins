import base64
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Dict

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from yarl import URL

@dataclass
class Credentials:
    base_url: str


class MineruTool(Tool):
    RETRY_INTERVAL = 5
    MAX_RETRIES = 3

    def _get_credentials(self) -> Credentials:
        """Get and validate credentials."""
        base_url = self.runtime.credentials.get("base_url")
        if not base_url:
            raise ToolProviderCredentialValidationError("Please input base_url")
        return Credentials(base_url=base_url)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {'accept': 'application/json'}

    def _build_api_url(self, base_url: str, *paths: str) -> str:
        return str(URL(base_url) / "/".join(paths))

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        credentials = self._get_credentials()
        yield from self.parser_pdf(credentials, tool_parameters)

    def validate_token(self) -> None:
        """Validate URL"""
        credentials = self._get_credentials()
        url = self._build_api_url(credentials.base_url, "docs")
        response = requests.get(url, headers=self._get_headers())
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError("Please check your base_url")

    def parser_pdf(
        self,
        credentials: Credentials,
        tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Parse PDF files."""
        files = tool_parameters.get("files")
        if not files:
            raise ValueError("File is required")

        headers = self._get_headers()
        task_url = self._build_api_url(credentials.base_url, "pdf_parse")
        params = {
            'parse_method': tool_parameters.get('parse_method', 'auto'),
            'return_layout': False,
            'return_info': False,
            'return_content_list': True,
            'return_images': True
        }

        for file in files:
            file_data = {
                "pdf_file": (file.filename, file.blob, 'application/pdf'),
            }
            response = self._post_with_retries(task_url, headers, params, file_data)

            response_json = response.json()
            md_content = response_json.get("md_content", "")
            content_list = response_json.get("content_list", [])
            file_obj = response_json.get("images",{})

            for file_name,encoded_image_data in file_obj.items():
                # Extract the base64 part of the data URI
                base64_data = encoded_image_data.split(",")[1]
                # Decode the base64 data to bytes
                image_bytes = base64.b64decode(base64_data)
                yield self.create_blob_message(image_bytes,meta={"filename":file_name,"mime_type":"image/jpeg"})

            yield self.create_text_message(md_content)
            yield self.create_json_message({"content_list":content_list})


    def _post_with_retries(self, url: str, headers: Dict[str, str], params: Dict[str, str], files: Dict[str, Any]) -> requests.Response:
        """Post request with retry mechanism."""
        for attempt in range(self.MAX_RETRIES):
            response = requests.post(url, headers=headers, params=params, files=files)
            if response.status_code == 200:
                return response
            elif attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_INTERVAL)
            else:
                raise RuntimeError("Failed to create extraction task after multiple attempts")