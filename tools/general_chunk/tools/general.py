from collections.abc import Generator
from typing import Any
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from .splitter.fixed_text_splitter import FixedRecursiveCharacterTextSplitter


class GeneralChunkTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke general chunk tool
        """
        input_variable = tool_parameters.get("input_variable", "")
        max_tokens = tool_parameters.get("max_chunk_length", 1000)
        chunk_overlap = tool_parameters.get("chunk_overlap_length", 100)
        separator = tool_parameters.get("delimiter", "。")

        character_splitter = FixedRecursiveCharacterTextSplitter.from_encoder(
            chunk_size=max_tokens,
            chunk_overlap=chunk_overlap,
            fixed_separator=separator,
            separators=["\n\n", "。", ". ", " ", ""],
        )

        chunks = character_splitter.split_text(input_variable)
        try:
            yield self.create_variable_message("result", chunks)
        except Exception as e:
            yield self.create_text_message(f"Error: {e}")
