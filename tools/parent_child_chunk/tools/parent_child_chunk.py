from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.entities.entities import Rule, Segmentation
from tools.index_processor.parent_child_index_processor import ParentChildIndexProcessor


class ParentChildChunkTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        input_text = tool_parameters.get("input_text")
        if not input_text:
            raise ValueError("input_text is required")
        parent_mode = tool_parameters.get("parent_mode", "paragraph")
        max_length = tool_parameters.get("max_length", 1024)
        separator = tool_parameters.get("separator", "\n\n")
        subchunk_max_length = tool_parameters.get("subchunk_max_length", 512)
        subchunk_separator = tool_parameters.get("subchunk_separator", "\n")
        remove_urls_emails = tool_parameters.get("remove_urls_emails", False)
        remove_extra_spaces = tool_parameters.get("remove_extra_spaces", False)

        rule = Rule()
        rule.parent_mode = parent_mode
        rule.segmentation = Segmentation(max_tokens=max_length, separator=separator)
        rule.subchunk_segmentation = Segmentation(max_tokens=subchunk_max_length, separator=subchunk_separator)
        rule.remove_urls_emails = remove_urls_emails
        rule.remove_extra_spaces = remove_extra_spaces
        parent_child_processor = ParentChildIndexProcessor()
        parent_child_structure_chunk = parent_child_processor.transform(
            input_text=input_text, rules=rule
        )
        yield self.create_variable_message("result", parent_child_structure_chunk)
