import re
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File


class ReplaceMdImgPathTool(Tool):

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        markdown_text = tool_parameters.get("markdown_text")
        file_list = tool_parameters.get("file_list")
        if not markdown_text or not file_list:
            raise ValueError("Both markdown_text and file_list are required")

        yield from self.replace_image_paths(markdown_text, file_list)

    def replace_image_paths(
        self,
        markdown_text: str,
        file_list: list[File]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Replace image paths in Markdown text with image URLs."""
        url_list = [file.url for file in file_list]
        image_link_pattern = r'!\[.*?\]\((.*?)\)'
        img_path_list =  re.findall(image_link_pattern, markdown_text)
        if len(url_list) != len(img_path_list):
            raise ValueError("Number of image URLs does not match number of image paths")
        for i in range(len(img_path_list)):
            markdown_text = markdown_text.replace(img_path_list[i], url_list[i])
        yield self.create_text_message(markdown_text)