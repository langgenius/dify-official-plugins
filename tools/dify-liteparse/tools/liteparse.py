import os
import tempfile
import logging
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# Core Engine: LiteParse (LlamaIndex)
try:
    from liteparse import Parser
except ImportError:
    Parser = None

logger = logging.getLogger(__name__)

class LiteparseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        file_obj = tool_parameters.get('file')

        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        if Parser is None:
            yield self.create_text_message("Error: 'liteparse' library is not correctly installed in this environment.")
            return

        # Initialize LiteParse Parser
        try:
            parser = Parser()
        except Exception as e:
            yield self.create_text_message(f"Failed to initialize LiteParse: {str(e)}")
            return

        temp_file_path = None
        try:
            # Handle the file object
            if isinstance(file_obj, list):
                file_obj = file_obj[0]
            
            # Use blob-to-tempfile strategy for sandbox compatibility
            if hasattr(file_obj, 'path') and file_obj.path:
                file_path = file_obj.path
            elif hasattr(file_obj, 'blob'):
                if callable(file_obj.blob):
                    content = file_obj.blob()
                else:
                    content = file_obj.blob
                
                ext = getattr(file_obj, 'extension', '.pdf')
                if ext and not ext.startswith('.'):
                    ext = f".{ext}"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp.write(content)
                    temp_file_path = tmp.name
                file_path = temp_file_path
            else:
                yield self.create_text_message(f"Error: Unsupported file object type: {str(type(file_obj))}")
                return

            # Convert document to Markdown using LiteParse
            try:
                # liteparse.parse() returns the markdown string
                markdown_output = parser.parse(file_path)
                
                if not markdown_output:
                    yield self.create_text_message("Warning: No content extracted.")
                    return
                
                yield self.create_text_message(markdown_output)
            except Exception as e:
                # This is where the Node.js "CLI not found" error will likely surface
                yield self.create_text_message(f"LiteParse execution failed: {str(e)}")

        except Exception as e:
            yield self.create_text_message(f"Tool error: {str(e)}")

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
