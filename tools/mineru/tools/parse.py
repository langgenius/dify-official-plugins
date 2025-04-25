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
from requests import post,get,put
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from yarl import URL

logger = logging.getLogger(__name__)

@dataclass
class Credentials:
    base_url: str
    token: str
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
        server_type = self.runtime.credentials.get("server_type")
        token = self.runtime.credentials.get("token")
        if not base_url:
            logger.error("Missing base_url in credentials")
            raise ToolProviderCredentialValidationError("Please input base_url")
        if server_type=="remote" and not token:
            logger.error("Missing token for remote server type")
            raise ToolProviderCredentialValidationError("Please input token")
        return Credentials(base_url=base_url, server_type=server_type, token=token)


    @staticmethod
    def _get_headers(credentials:Credentials) -> Dict[str, str]:
        """Get request headers."""
        if credentials.server_type=="remote":
            return {
                'Authorization': f'Bearer {credentials.token}',
                'Content-Type':'application/json',
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
        if credentials.server_type=="local":
            url = self._build_api_url(credentials.base_url, "docs")
            logger.info(f"Validating local server connection to {url}")
            response = get(url, headers=self._get_headers(credentials),timeout=10)
            if response.status_code != 200:
                logger.error(f"Local server validation failed with status {response.status_code}")
                raise ToolProviderCredentialValidationError("Please check your base_url")
        elif credentials.server_type=="remote":
            url = self._build_api_url(credentials.base_url, "api/v4/file-urls/batch")
            logger.info(f"Validating remote server connection to {url}")
            response = post(url, headers=self._get_headers(credentials),timeout=10)
            if response.status_code!= 200:
                logger.error(f"Remote server validation failed with status {response.status_code}")
                raise ToolProviderCredentialValidationError("Please check your base_url and token")


    def _parser_file_local(self, credentials: Credentials, tool_parameters: Dict[str, Any]):
        """Parse files by local server."""
        file = tool_parameters.get("file")
        if not file:
            logger.error("No file provided for file parsing")
            raise ValueError("File is required")

        self._validate_file_type(file.filename)

        headers = self._get_headers(credentials)
        task_url = self._build_api_url(credentials.base_url, "file_parse")
        logger.info(f"Starting file parse request to {task_url}")
        params = {
            'parse_method': tool_parameters.get('parse_method', 'auto'),
            'return_layout': False,
            'return_info': False,
            'return_content_list': True,
            'return_images': True
        }

        file_data = {
            "file": (file.filename, file.blob),
        }
        response = post(task_url, headers=headers, params=params, files=file_data)
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
            base64_data = encoded_image_data.split(",")[1]
            image_bytes = base64.b64decode(base64_data)
            file_res = self.session.file.upload(
                file_name,
                image_bytes,
                "image/jpeg"
            )
            images.append(file_res)
            if not file_res.preview_url:
                yield self.create_blob_message(image_bytes, meta={"filename": file_name, "mime_type": "image/jpeg"})


        md_content = self._replace_md_img_path(md_content, images)
        yield self.create_variable_message("images", images)
        yield self.create_text_message(md_content)
        yield self.create_json_message({"content_list": content_list})


    def _parser_file_remote(self, credentials: Credentials, tool_parameters: Dict[str, Any]):
        """Parse files by remote server."""
        file = tool_parameters.get("file")
        if not file:
            logger.error("No file provided for file parsing")
            raise ValueError("File is required")
        self._validate_file_type(file.filename)

        header = self._get_headers(credentials)

        # create parsing task
        data = {
            "enable_formula": tool_parameters.get("enable_formula", True),
            "enable_table": tool_parameters.get("enable_table", True),
            "language": tool_parameters.get("language", "auto"),
            "layout_model": tool_parameters.get("layout_model", "doclayout_yolo"),
            "extra_formats": json.loads(tool_parameters.get("extra_formats", "[]")),
            "files": [
                {"name": file.filename, "is_ocr": tool_parameters.get("enable_ocr",False)}
            ]
        }
        task_url = self._build_api_url(credentials.base_url, "api/v4/file-urls/batch")
        response = post(task_url, headers=header, json=data)

        if response.status_code != 200:
            logger.error('apply upload url failed. status:{} ,result:{}'.format(response.status_code, response.text))
            raise Exception('apply upload url failed. status:{} ,result:{}'.format(response.status_code, response.text))

        result = response.json()

        if result["code"] == 0:
            logger.info('apply upload url success,result:{}'.format(result))
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]

            res_upload = put(urls[0], data=file.blob)
            if res_upload.status_code == 200:
                logger.info(f"{urls[0]} upload success")
            else:
                logger.error(f"{urls[0]} upload failed")
                raise Exception(f"{urls[0]} upload failed")

            extract_result = self._poll_get_parse_result(credentials, batch_id)

            yield from self._download_and_extract_zip(extract_result.get("full_zip_url"))
            yield self.create_variable_message("full_zip_url", extract_result.get("full_zip_url"))
        else:
            logger.error('apply upload url failed,reason:{}'.format(result.msg))
            raise Exception('apply upload url failed,reason:{}'.format(result.msg))


    def _poll_get_parse_result(self, credentials: Credentials, batch_id: str) -> Dict[str, Any]:
        """poll get parser result."""
        url = self._build_api_url(credentials.base_url, f"api/v4/extract-results/batch/{batch_id}")
        headers = self._get_headers(credentials)
        max_retries = 50
        retry_interval = 5

        for _ in range(max_retries):
            response = get(url, headers=headers)
            if response.status_code == 200:
                data = response.json().get("data", {})
                extract_result = data.get("extract_result", {})[0]
                if extract_result.get("state") == "done":
                    logger.info("Parse completed successfully")
                    return extract_result
                if extract_result.get("state") == "failed":
                    logger.error(f"Parse failed, reason: {extract_result.get('err_msg')}")
                    raise Exception(f"Parse failed, reason: {extract_result.get('err_msg')}")
                logger.info(f"Parse in progress, state: {extract_result.get('state')}")
            else:
                logger.warning(f"Failed to get parse result, status: {response.status_code}")
                raise Exception(f"Failed to get parse result, status: {response.status_code}")

            time.sleep(retry_interval)

        logger.error("Polling timeout reached without getting completed result")
        raise TimeoutError("Parse operation timed out")


    def _download_and_extract_zip(self, url: str) -> Generator[ToolInvokeMessage, None, None]:
        """Download and extract zip file from URL."""
        response = httpx.get(url)
        response.raise_for_status()

        content = ZipContent()

        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            for file_info in zip_file.infolist():
                if file_info.is_dir():
                    continue

                file_name = file_info.filename.lower()
                with zip_file.open(file_info) as f:
                    if file_name.startswith("images/") and file_name.endswith(('.png', '.jpg', '.jpeg')):
                        image_bytes = f.read()
                        upload_file_res = self._process_image(image_bytes, file_info)
                        content.images.append(upload_file_res)
                        if not upload_file_res.preview_url:
                            base_name = os.path.basename(file_info.filename)
                            yield self.create_blob_message(image_bytes,
                                                           meta={"filename": base_name, "mime_type": "image/jpeg"})
                    elif file_name.endswith(".md"):
                        content.md_content = f.read().decode('utf-8')
                    elif file_name.endswith('.json') and file_name != "layout.json":
                        content.content_list.append(json.loads(f.read().decode('utf-8')))
                    elif file_name.endswith('.html'):
                        content.html_content = f.read().decode('utf-8')
                        yield self.create_blob_message(content.html_content,
                                                       meta={"filename":file_name,"mime_type":"text/html"})
                    elif file_name.endswith('.docx'):
                        content.docx_content = f.read()
                        yield self.create_blob_message(content.docx_content,
                                                       meta={"filename":file_name,"mime_type":"application/msword"})
                    elif file_name.endswith('.tex'):
                        content.latex_content = f.read().decode('utf-8')
                        yield self.create_blob_message(content.latex_content,
                                                       meta={"filename":file_name,"mime_type":"application/x-tex"})
        yield self.create_json_message({"content_list": content.content_list})
        content.md_content = self._replace_md_img_path(content.md_content, content.images)
        yield self.create_text_message(content.md_content)
        yield self.create_variable_message("images", content.images)


    def _process_image(self, image_bytes:bytes, file_info: zipfile.ZipInfo) -> UploadFileResponse:
        """Process an image file from the zip archive."""
        base_name = os.path.basename(file_info.filename)
        return self.session.file.upload(
            base_name,
            image_bytes,
            "image/jpeg"
        )


    @staticmethod
    def _replace_md_img_path(md_content: str, images: list[UploadFileResponse]) -> str:
        for image in images:
            if image.preview_url:
                md_content = md_content.replace("images/"+image.name, image.preview_url)
        return md_content

    @staticmethod
    def _validate_file_type(filename: str) -> str:
        extension = os.path.splitext(filename)[1].lower()
        if extension not in [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"]:
            raise ValueError(f"File extension {extension} is not supported")
        return extension


    def parser_file(
        self,
        credentials: Credentials,
        tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        if credentials.server_type=="local":
            yield from self._parser_file_local(credentials, tool_parameters)
        elif credentials.server_type=="remote":
            yield from self._parser_file_remote(credentials, tool_parameters)


