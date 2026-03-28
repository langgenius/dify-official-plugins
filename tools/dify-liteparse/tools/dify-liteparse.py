from collections.abc import Generator
from typing import Any
import tempfile
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from liteparse import LiteParse # This requires liteparse in requirements.txt

class DifyLiteparseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # Fetch API key from provider settings if not provided in the node parameters
        api_key = tool_parameters.get('api_key') or self.provider_credentials.get('api_key')
        file_obj = tool_parameters.get('file')

        if not api_key:
            yield self.create_text_message("Error: LlamaCloud API Key is missing.")
            return
        
        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        try:
            # 2. Initialize LiteParse
            parser = LiteParse(api_key=api_key)

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
            documents = parser.load_data(file_path)
            
            # 5. Extract the text and yield it back to Dify
            if not documents:
                yield self.create_text_message("Warning: No content extracted from the document.")
                return
                
            final_text = "\n\n".join([doc.text for doc in documents])
            
            yield self.create_text_message(final_text)

        except Exception as e:
            yield self.create_text_message(f"Parsing failed with error: {str(e)}")