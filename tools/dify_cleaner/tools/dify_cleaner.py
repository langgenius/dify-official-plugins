import re
import uuid
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DifyCleanerTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # default clean
        # remove invalid symbol
        text = tool_parameters.get("text", "")
        remove_extra_spaces = tool_parameters.get("remove_extra_spaces", False)
        remove_urls_emails = tool_parameters.get("remove_urls_emails", False)
        text = re.sub(r"<\|", "<", text)
        text = re.sub(r"\|>", ">", text)
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\xEF\xBF\xBE]", "", text)
        # Unicode  U+FFFE
        text = re.sub("\ufffe", "", text)

        if remove_extra_spaces:
            # Remove extra spaces
            pattern = r"\n{3,}"
            text = re.sub(pattern, "\n\n", text)
            pattern = (
                r"[\t\f\r\x20\u00a0\u1680\u180e\u2000-\u200a\u202f\u205f\u3000]{2,}"
            )
            text = re.sub(pattern, " ", text)
        if remove_urls_emails:
            # Precompile regular expressions
            email_pattern = re.compile(
                r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"
            )
            markdown_image_pattern = re.compile(r"!\[.*?\]\((https?://[^\s)]+)\)")
            url_pattern = re.compile(r"https?://[^\s)]+")

            # Remove email addresses
            text = email_pattern.sub("", text)

            # Remove URL but keep Markdown image URLs
            placeholder_map = {}

            def replace_image(match):
                _placeholder_id = f"__MD_IMG_{uuid.uuid4().hex}__"
                placeholder_map[_placeholder_id] = match.group(1)
                return f"![image]({_placeholder_id})"

            # First, temporarily replace Markdown image URLs with a placeholder
            text = markdown_image_pattern.sub(replace_image, text)
            # Now remove all remaining URLs
            text = url_pattern.sub("", text)
            # Finally, restore the Markdown image URLs
            for placeholder_id, url in placeholder_map.items():
                text = text.replace(placeholder_id, url)

        yield self.create_text_message(text)
