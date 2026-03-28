from collections.abc import Generator
from typing import Any
import tempfile
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from liteparse import LiteParse # This requires liteparse in requirements.txt

class DifyLiteparseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file_obj = tool_parameters.get('file')

        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        try:
            # 2. Initialize LiteParse (Local-first, no API key needed)
            parser = LiteParse()

            # 3. Handle the file
            # Dify provides a file object or a list of file objects.
            # If it's a list, we take the first one.
            if isinstance(file_obj, list):
                if not file_obj:
                    yield self.create_text_message("Error: No file uploaded.")
                    return
                file_obj = file_obj[0]

            # Extract the local path from the Dify file object.
            # In the Dify Plugin SDK, file objects have a 'path' attribute.
            if isinstance(file_obj, dict):
                file_path = file_obj.get('path')
            else:
                file_path = file_obj # Fallback if it's already a string

            if not file_path:
                yield self.create_text_message("Error: File path could not be determined.")
                return

            # 4. Run the parser
            # liteparse usually returns a list of Document objects
            print(f"🚀 Parsing file: {file_path}")
            result = parser.parse(file_path)
            
            if not result or not result.text:
                yield self.create_text_message("Warning: No content extracted.")
                return
                
            yield self.create_text_message(result.text)

        except Exception as e:
            yield self.create_text_message(f"Parsing failed with error: {str(e)}")