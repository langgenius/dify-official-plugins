import os
import tempfile
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# Core Engine: Docling
from docling.document_converter import DocumentConverter

class LiteParseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file_obj = tool_parameters.get('file')

        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        # Initialize Docling Converter
        try:
            converter = DocumentConverter()
        except Exception as e:
            yield self.create_text_message(f"Failed to initialize Docling engine: {str(e)}")
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
                yield self.create_text_message(f"Error: Unsupported file object type: {type(file_obj)}")
                return

            # Convert document to Markdown using Docling
            result = converter.convert(file_path)
            markdown_output = result.document.export_to_markdown()
            
            if not markdown_output:
                yield self.create_text_message("Warning: No content extracted.")
                return
            
            yield self.create_text_message(markdown_output)

        except Exception as e:
            yield self.create_text_message(f"Parsing failed: {str(e)}")

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
