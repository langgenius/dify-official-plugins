import base64
import json
import logging
import zlib
from collections.abc import Generator
from dataclasses import dataclass
from mimetypes import guess_extension
from typing import Any
from urllib.parse import urlparse

import requests
import unstructured_client
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from unstructured_client.models import operations, shared

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
    api_url: str
    api_key: str
    server_type: str


class PartitionTool(Tool):
    def _get_credentials(self) -> Credentials:
        """Get and validate credentials."""
        api_url = self.runtime.credentials.get("api_url")
        server_type = self.runtime.credentials.get("server_type")
        api_key = self.runtime.credentials.get("api_key")
        if not api_url:
            logger.exception("Missing api_url in credentials")
            raise ToolProviderCredentialValidationError("Please input api_url")
        if server_type == "remote" and not api_key:
            logger.error("Missing api_key for remote server type")
            raise ToolProviderCredentialValidationError("Please input api_key")
        return Credentials(api_url=api_url, server_type=server_type, api_key=api_key)

    def validate_api_url(self) -> None:
        """Validate URL and api_key."""
        credentials = self._get_credentials()
        try:
            headers = {
                "accept": "application/json",
                "unstructured-api-key": credentials.api_key,
            }
            parsed = urlparse(credentials.api_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            response = requests.get(base_url + "/healthcheck", headers=headers)
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError("Please check your api_url")
        except Exception as e:
            logger.exception(f"Validate api_url failed. msg: {e}")
            raise ToolProviderCredentialValidationError(
                f"validate api_url failed. reason:{e}"
            )

    @staticmethod
    def extract_orig_elements(orig_elements):
        decoded_orig_elements = base64.b64decode(orig_elements)
        decompressed_orig_elements = zlib.decompress(decoded_orig_elements)
        return decompressed_orig_elements.decode("utf-8")

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        credentials = self._get_credentials()
        client = unstructured_client.UnstructuredClient(
            server_url=credentials.api_url,
            api_key_auth=credentials.api_key,
        )

        file = tool_parameters.get("file")

        req = operations.PartitionRequest(
            partition_parameters=shared.PartitionParameters(
                files=shared.Files(
                    content=file.blob,
                    file_name=file.filename,
                ),
                strategy=tool_parameters.get("strategy", "hi_res"),
                vlm_model=tool_parameters.get("vlm_model", "gpt-4o"),
                vlm_model_provider=tool_parameters.get("vlm_model_provider", "openai"),
                languages=json.loads(
                    tool_parameters.get("languages", "[]")
                    if tool_parameters.get("languages")
                    else "[]"
                ),
                chunking_strategy=tool_parameters.get("chunking_strategy", None),
                max_characters=tool_parameters.get("max_characters", 500),
                overlap=tool_parameters.get("overlap", 0),
                **{
                    k: v
                    for k, v in json.loads(
                        tool_parameters.get("advanced_options", "{}")
                    ).items()
                    if k
                    in [
                        "coordinates",
                        "content_type",
                        "encoding",
                        "extract_image_block_types",
                        "gz_uncompressed_content_type",
                        "include_page_breaks",
                        "ocr_languages",
                        "output_format",
                        "pdf_infer_table_structure",
                        "skip_infer_table_types",
                        "starting_page_number",
                        "unique_element_ids",
                        "xml_keep_tags",
                        "combine_under_n_chars",
                        "include_orig_elements",
                        "multipage_sections",
                        "new_after_n_chars",
                        "overlap",
                        "overlap_all",
                        "similarity_threshold",
                    ]
                    and v is not None
                },
            ),
        )
        try:
            res = client.general.partition(request=req)

            text = ""
            images = []
            elements = res.elements
            for element in elements:
                if element["type"] == "Image":
                    base64_data = element["metadata"]["image_base64"]
                    image_bytes = base64.b64decode(base64_data)
                    mime_type = element["metadata"]["image_mime_type"]
                    extension = guess_extension(mime_type)
                    image_name = f"image_{element['element_id']}{extension}"
                    file_res = self.session.file.upload(
                        element["element_id"],
                        image_bytes,
                        mimetype=mime_type,
                    )
                    images.append(file_res)
                    element["metadata"]["preview_url"] = file_res.preview_url
                    element["metadata"]["dify_file_id"] = file_res.id
                    element["metadata"].pop("image_base64")
                    text += f"![]({file_res.preview_url})\n"
                    if not file_res.preview_url:
                        yield self.create_blob_message(
                            image_bytes,
                            meta={"filename": image_name, "mime_type": mime_type},
                        )

                if "orig_elements" in element["metadata"]:
                    # ...get the chunk's associated elements in context...
                    orig_elements = json.loads(
                        self.extract_orig_elements(element["metadata"]["orig_elements"])
                    )

                    for orig_element in orig_elements:
                        if orig_element["type"] == "Image":
                            if orig_element["metadata"].get("image_base64"):
                                base64_data = orig_element["metadata"]["image_base64"]
                                image_bytes = base64.b64decode(base64_data)
                                mime_type = orig_element["metadata"]["image_mime_type"]
                                extension = guess_extension(mime_type)
                                image_name = (
                                    f"image_{orig_element['element_id']}{extension}"
                                )
                                file_res = self.session.file.upload(
                                    orig_element["element_id"],
                                    image_bytes,
                                    mimetype=mime_type,
                                )
                                images.append(file_res)
                                orig_element["metadata"]["preview_url"] = (
                                    file_res.preview_url
                                )
                                orig_element["metadata"]["dify_file_id"] = file_res.id
                                orig_element["metadata"].pop("image_base64")
                                text += f"![]({file_res.preview_url})\n"

                    element["metadata"]["orig_elements"] = orig_elements

                text += element["text"]

            yield self.create_text_message(text)
            yield self.create_variable_message("images", images)
            yield self.create_variable_message("elements", elements)
        except Exception as e:
            logger.exception(f"Partition request failed. msg:{e} ")
            raise Exception(f"Partition request failed. msg:{e}")
