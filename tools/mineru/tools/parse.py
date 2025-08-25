import base64
import io
import json
import logging
import os
import time
import zipfile
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from dify_plugin.invocations.file import UploadFileResponse
from requests import Response, post, get, put
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from yarl import URL

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}
MAX_RETRIES = 50
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}


@dataclass
class Credentials:
    base_url: str
    token: str | None
    server_type: str

@dataclass
class ZipContent:
    md_content: str = ""
    content_list: List[Dict[str, Any]] = None
    images: List[UploadFileResponse] = None
    html_content: Optional[str] = None
    docx_content: Optional[bytes] = None
    latex_content: Optional[str] = None

    def __post_init__(self):
        if self.content_list is None:
            self.content_list = []
        if self.images is None:
            self.images = []


class MineruTool(Tool):

    def _get_credentials(self) -> Credentials:
        """Get and validate credentials."""
        base_url = self.runtime.credentials.get("base_url")
        server_type = self.runtime.credentials.get("server_type", "local")
        token = self.runtime.credentials.get("token")
        
        if not base_url:
            logger.error("Missing base_url in credentials")
            raise ToolProviderCredentialValidationError("Please input base_url")
        
        if server_type == "remote" and not token:
            logger.error("Missing token for remote server type")
            raise ToolProviderCredentialValidationError("Please input token")
        
        return Credentials(base_url=base_url, server_type=server_type, token=token)

    @staticmethod
    def _get_headers(credentials: Credentials) -> Dict[str, str]:
        """Get request headers."""
        if credentials.server_type == "remote":
            return {
                'Authorization': f'Bearer {credentials.token}',
                'Content-Type': 'application/json',
            }
        return {
            'accept': 'application/json'
        }

    @staticmethod
    def _build_api_url(base_url: str, *paths: str) -> str:
        return str(URL(base_url) / "/".join(paths))

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        credentials = self._get_credentials()
        yield from self.parser_file(credentials, tool_parameters)

    def validate_token(self) -> None:
        """Validate URL and token."""
        credentials = self._get_credentials()
        
        if credentials.server_type == "local":
            self._validate_local_server(credentials)
        elif credentials.server_type == "remote":
            self._validate_remote_server(credentials)

    def _validate_local_server(self, credentials: Credentials) -> None:
        """Validate local server connection"""
        url = self._build_api_url(credentials.base_url, "docs")
        logger.info(f"Validating local server connection to {url}")
        
        try:
            response = get(url, headers=self._get_headers(credentials), timeout=10)
            if response.status_code != 200:
                logger.error(f"Local server validation failed with status {response.status_code}")
                raise ToolProviderCredentialValidationError("Please check your base_url")
        except Exception as e:
            logger.error(f"Local server validation failed: {e}")
            raise ToolProviderCredentialValidationError("Please check your base_url")

    def _validate_remote_server(self, credentials: Credentials) -> None:
        """Validate remote server connection"""
        url = self._build_api_url(credentials.base_url, "api/v4/file-urls/batch")
        logger.info(f"Validating remote server connection to {url}")
        
        try:
            response = post(url, headers=self._get_headers(credentials), timeout=10)
            if response.status_code != 200:
                logger.error(f"Remote server validation failed with status {response.status_code}")
                raise ToolProviderCredentialValidationError("Please check your base_url and token")
        except Exception as e:
            logger.error(f"Remote server validation failed: {e}")
            raise ToolProviderCredentialValidationError("Please check your base_url and token")

    def _upload_image_to_dify(self, image_bytes: bytes, file_name: str) -> UploadFileResponse:
        return self.session.file.upload(
            file_name,
            image_bytes,
            "image/jpeg"
        )

    def _process_base64_image(self, encoded_image_data: str, file_name: str) -> UploadFileResponse:
        try:
            base64_data = encoded_image_data.split(",")[1]
            image_bytes = base64.b64decode(base64_data)
            return self._upload_image_to_dify(image_bytes, file_name)
        except (IndexError, ValueError) as e:
            logger.error(f"Failed to decode base64 image {file_name}: {e}")
            raise ValueError(f"Invalid base64 image data for {file_name}")

    def _parse_local_v1(self, credentials: Credentials, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Parse local file by v1 api"""
        params = {
            'parse_method': tool_parameters.get('parse_method', 'auto'),
            'return_layout': False,
            'return_info': False,
            'return_content_list': True,
            'return_images': True
        }

        file = tool_parameters.get("file")
        if not file:
            logger.error("No file provided for file parsing")
            raise ValueError("File is required")

        headers = self._get_headers(credentials)
        task_url = self._build_api_url(credentials.base_url, "file_parse")
        file_data = {"file": (file.filename, file.blob)}

        logger.info(f"Starting file parse request to {task_url} by v1 api")
        
        try:
            response = post(task_url, headers=headers, params=params, files=file_data)
        except Exception as e:
            logger.error(f"Request failed: {e}")
            yield self.create_text_message(f"Failed to connect to server: {e}")
            return

        if response.status_code != 200:
            logger.error(f"File parse failed with status {response.status_code}")
            yield self.create_text_message(f"Failed to parse file. result: {response.text}")
            return

        logger.info("File parse completed successfully")
        response_json = response.json()
        md_content = response_json.get("md_content", "")
        content_list = response_json.get("content_list", [])
        file_obj = response_json.get("images", {})

        images = []
        for file_name, encoded_image_data in file_obj.items():
            try:
                file_res = self._process_base64_image(encoded_image_data, file_name)
                images.append(file_res)
                if not file_res.preview_url:
                    yield self.create_blob_message(
                        base64.b64decode(encoded_image_data.split(",")[1]), 
                        meta={"filename": file_name, "mime_type": "image/jpeg"}
                    )
            except Exception as e:
                logger.error(f"Failed to process image {file_name}: {e}")

        md_content = self._replace_md_img_path(md_content, images)
        yield self.create_variable_message("images", images)
        yield self.create_text_message(md_content)
        yield self.create_json_message({"content_list": content_list})

    def _parse_local_v2(self, credentials: Credentials, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        lang_list = ["ch"]
        if tool_parameters.get('language') and tool_parameters.get('language') != "auto":
            lang_list = tool_parameters.get('language')

        body = {
            'parse_method': tool_parameters.get('parse_method', 'auto'),
            'return_md': True,
            'return_model_output': False,
            'return_content_list': True,
            'lang_list': lang_list,
            'return_images': True,
            'backend': tool_parameters.get('backend', 'pipeline'),
            'formula_enable': tool_parameters.get('formula_enable', True),
            'table_enable': tool_parameters.get('table_enable', True),
            'server_url': tool_parameters.get('sglang_server_url', ""),
            'return_middle_json': False,
        }

        file = tool_parameters.get("file")
        headers = self._get_headers(credentials)
        task_url = self._build_api_url(credentials.base_url, "file_parse")
        file_data = [("files", (file.filename, file.blob))]
        
        try:
            response = post(task_url, headers=headers, data=body, files=file_data)
        except Exception as e:
            logger.error(f"Request failed: {e}")
            yield self.create_text_message(f"Failed to connect to server: {e}")
            return

        if self._is_api_v1(response):
            yield from self._parse_local_v1(credentials, tool_parameters)
            return
        elif response.status_code != 200:
            logger.error(f"File parse failed with status {response.status_code}")
            yield self.create_text_message(f"Failed to parse file. result: {response.text}")
            return
        
        logger.info("File parse completed successfully")
        response_json = response.json()
        results = response_json.get("results", {})

        for file_name, result in results.items():
            result_item = {"filename": file_name}

            if result.get("images"):
                result_item["images"] = []
                for img_name, encoded_image_data in result["images"].items():
                    try:
                        file_res = self._process_base64_image(encoded_image_data, img_name)
                        result_item["images"].append(file_res)
                        if not file_res.preview_url:
                            yield self.create_blob_message(
                                base64.b64decode(encoded_image_data.split(",")[1]), 
                                meta={"filename": img_name, "mime_type": "image/jpeg"}
                            )
                    except Exception as e:
                        logger.error(f"Failed to process image {img_name}: {e}")
                
                yield self.create_variable_message("images", result_item["images"])

            if result.get("content_list"):
                try:
                    result_item["content_list"] = json.loads(result["content_list"])
                    yield self.create_json_message({"content_list": result_item["content_list"]})
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse content_list JSON: {e}")

            if result.get("md_content"):
                result_item["md_content"] = result["md_content"]
                if result_item.get("images"):
                    result_item["md_content"] = self._replace_md_img_path(result_item["md_content"], result_item["images"])
                yield self.create_text_message(result_item["md_content"])

        yield self.create_json_message({"_result": result_item})

    def _is_api_v1(self, response: Response) -> bool:
        try:
            detail = response.json().get("detail")
            if isinstance(detail, list) and response.status_code == 422:
                for item in detail:
                    if (item.get("type") == "missing" and 
                        item.get("loc") and 
                        len(item.get("loc")) >= 2 and
                        item.get("loc")[0] == "body" and 
                        item.get("loc")[1] == "file"):
                        return True
            return False
        except Exception:
            return False

    def _parser_file_local(self, credentials: Credentials, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        file = tool_parameters.get("file", None)
        if not file:
            logger.error("No file provided for file parsing")
            raise ValueError("File is required")

        self._validate_file_type(file.filename)

        yield from self._parse_local_v2(credentials, tool_parameters)

    def _parser_file_remote(self, credentials: Credentials, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        file = tool_parameters.get("file", None)
        if not file:
            logger.error("No file provided for file parsing")
            raise ValueError("File is required")

        self._validate_file_type(file.filename)

        header = self._get_headers(credentials)

        # Create parsing task
        data = {
            "enable_formula": tool_parameters.get("enable_formula", True),
            "enable_table": tool_parameters.get("enable_table", True),
            "language": tool_parameters.get("language", "auto"),
            "layout_model": tool_parameters.get("layout_model", "doclayout_yolo"),
            "extra_formats": json.loads(tool_parameters.get("extra_formats", "[]")),
            "files": [{"name": file.filename, "is_ocr": tool_parameters.get("enable_ocr", False)}]
        }
        
        task_url = self._build_api_url(credentials.base_url, "api/v4/file-urls/batch")
        
        try:
            response = post(task_url, headers=header, json=data)
        except Exception as e:
            logger.error(f"Failed to create parsing task: {e}")
            raise Exception(f"Failed to create parsing task: {e}")

        if response.status_code != 200:
            logger.error(f'Apply upload url failed. status:{response.status_code}, result:{response.text}')
            raise Exception(f'Apply upload url failed. status:{response.status_code}, result:{response.text}')

        result = response.json()

        if result["code"] == 0:
            logger.info(f'Apply upload url success, result:{result}')
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]

            res_upload = put(urls[0], data=file.blob)
            if res_upload.status_code == 200:
                logger.info(f"{urls[0]} upload success")
            else:
                logger.error(f"{urls[0]} upload failed")
                raise Exception(f"{urls[0]} upload failed")

            extract_result = self._poll_get_parse_result(credentials, batch_id)
            
            full_zip_url = extract_result.get("full_zip_url")
            if full_zip_url:
                yield from self._download_and_extract_zip(full_zip_url)
                yield self.create_variable_message("full_zip_url", full_zip_url)
            else:
                logger.error("No zip URL found in parse result")
                raise Exception("No zip URL found in parse result")
        else:
            logger.error(f'Apply upload url failed, reason:{result.get("msg", "Unknown error")}')
            raise Exception(f'Apply upload url failed, reason:{result.get("msg", "Unknown error")}')

    def _poll_get_parse_result(self, credentials: Credentials, batch_id: str) -> Dict[str, Any]:
        """poll get parser result."""
        url = self._build_api_url(credentials.base_url, f"api/v4/extract-results/batch/{batch_id}")
        headers = self._get_headers(credentials)

        for attempt in range(MAX_RETRIES):
            try:
                response = get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    extract_results = data.get("extract_result", [])
                    
                    if not extract_results:
                        logger.warning("No extract results found")
                        continue
                    
                    extract_result = extract_results[0]
                    state = extract_result.get("state")
                    
                    if state == "done":
                        logger.info("Parse completed successfully")
                        return extract_result
                    elif state == "failed":
                        err_msg = extract_result.get('err_msg', 'Unknown error')
                        logger.error(f"Parse failed, reason: {err_msg}")
                        raise Exception(f"Parse failed, reason: {err_msg}")
                    else:
                        logger.info(f"Parse in progress, state: {state}")
                else:
                    logger.warning(f"Failed to get parse result, status: {response.status_code}")
                    if attempt == MAX_RETRIES - 1:
                        raise Exception(f"Failed to get parse result, status: {response.status_code}")
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise e
                logger.warning(f"Poll attempt {attempt + 1} failed: {e}")

            time.sleep(5)

        logger.error("Polling timeout reached without getting completed result")
        raise TimeoutError("Parse operation timed out")

    def _download_and_extract_zip(self, url: str) -> Generator[ToolInvokeMessage, None, None]:
        """Download and extract zip file from URL."""
        try:
            response = httpx.get(url)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to download zip file: {e}")
            raise Exception(f"Failed to download zip file: {e}")

        content = ZipContent()

        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                for file_info in zip_file.infolist():
                    if file_info.is_dir():
                        continue

                    file_name = file_info.filename.lower()
                    with zip_file.open(file_info) as f:
                        yield from self._process_zip_file(f, file_info, file_name, content)
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid zip file: {e}")
            raise Exception(f"Invalid zip file: {e}")
        except Exception as e:
            logger.error(f"Failed to extract zip file: {e}")
            raise Exception(f"Failed to extract zip file: {e}")

        yield self.create_json_message({"content_list": content.content_list})
        content.md_content = self._replace_md_img_path(content.md_content, content.images)
        yield self.create_text_message(content.md_content)
        yield self.create_variable_message("images", content.images)

    def _process_zip_file(self, f, file_info: zipfile.ZipInfo, file_name: str, content: ZipContent) -> Generator[ToolInvokeMessage, None, None]:
        """Process single file from ZIP archive."""
        try:
            if file_name.startswith("images/") and file_name.endswith(tuple(SUPPORTED_IMAGE_EXTENSIONS)):
                image_bytes = f.read()
                upload_file_res = self._process_image(image_bytes, file_info)
                content.images.append(upload_file_res)
                if not upload_file_res.preview_url:
                    base_name = os.path.basename(file_info.filename)
                    yield self.create_blob_message(
                        image_bytes,
                        meta={"filename": base_name, "mime_type": "image/jpeg"}
                    )
            elif file_name.endswith(".md"):
                content.md_content = f.read().decode('utf-8')
            elif file_name.endswith('.json') and file_name != "layout.json":
                content.content_list.append(json.loads(f.read().decode('utf-8')))
            elif file_name.endswith('.html'):
                html_content = f.read().decode('utf-8')
                content.html_content = html_content
                yield self.create_blob_message(
                    html_content.encode('utf-8'),
                    meta={"filename": file_name, "mime_type": "text/html"}
                )
            elif file_name.endswith('.docx'):
                docx_content = f.read()
                content.docx_content = docx_content
                yield self.create_blob_message(
                    docx_content,
                    meta={"filename": file_name, "mime_type": "application/msword"}
                )
            elif file_name.endswith('.tex'):
                latex_content = f.read().decode('utf-8')
                content.latex_content = latex_content
                yield self.create_blob_message(
                    latex_content.encode('utf-8'),
                    meta={"filename": file_name, "mime_type": "application/x-tex"}
                )
        except Exception as e:
            logger.error(f"Failed to process file {file_name}: {e}")

    def _process_image(self, image_bytes: bytes, file_info: zipfile.ZipInfo) -> UploadFileResponse:
        """Process image file from ZIP archive."""
        base_name = os.path.basename(file_info.filename)
        return self.session.file.upload(
            base_name,
            image_bytes,
            "image/jpeg"
        )

    @staticmethod
    def _replace_md_img_path(md_content: str, images: List[UploadFileResponse]) -> str:
        """Replace image path in Markdown."""
        for image in images:
            if image.preview_url:
                md_content = md_content.replace(f"images/{image.name}", image.preview_url)
        return md_content

    @staticmethod
    def _validate_file_type(filename: str) -> str:
        """Validate file type."""
        extension = os.path.splitext(filename)[1].lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"File extension {extension} is not supported. Supported extensions: {SUPPORTED_EXTENSIONS}")
        return extension

    def parser_file(
        self,
        credentials: Credentials,
        tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Main entry point for parsing file."""
        if credentials.server_type == "local":
            yield from self._parser_file_local(credentials, tool_parameters)
        elif credentials.server_type == "remote":
            yield from self._parser_file_remote(credentials, tool_parameters)
        else:
            raise ValueError(f"Unsupported server type: {credentials.server_type}")


