from collections.abc import Generator
from typing import Any
import tempfile
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from liteparse import LiteParse # This requires liteparse in requirements.txt

class DifyLiteparseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # Update PATH to include Node.js bin directory (NVM)
        # This is necessary for local Dify installations to find the 'lit' CLI
        nvm_bin = "/Users/serdalaslantas/.nvm/versions/node/v24.13.1/bin"
        if os.path.exists(nvm_bin) and nvm_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = nvm_bin + os.pathsep + os.environ.get("PATH", "")

        file_obj = tool_parameters.get('file')

        if not file_obj:
            yield self.create_text_message("Error: No file uploaded.")
            return

        try:
            # Pass common absolute paths to find 'liteparse' CLI (or legacy 'lit')
            possible_cli_paths = [
                "/Users/serdalaslantas/.nvm/versions/node/v24.13.1/bin/liteparse",
                "/Users/serdalaslantas/.nvm/versions/node/v24.13.1/bin/lit",
                "/usr/local/bin/liteparse",
                "/usr/local/bin/lit",
                "/opt/homebrew/bin/liteparse",
                "/opt/homebrew/bin/lit",
            ]
            cli_path = None
            for p in possible_cli_paths:
                if os.path.exists(p):
                    cli_path = p
                    break
            
            if cli_path:
                parser = LiteParse(cli_path=cli_path)
            else:
                # Fallback to default but pass debug info if it fails later
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
            temp_file_path = None
            try:
                if isinstance(file_obj, dict):
                    file_path = file_obj.get('path')
                elif isinstance(file_obj, str):
                    file_path = file_obj
                elif hasattr(file_obj, 'path') and file_obj.path:
                    file_path = file_obj.path
                elif hasattr(file_obj, 'blob'):
                    # Retrieve the binary content and save to a temporary file
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
                    file_path = None

                if not file_path:
                    attrs = [a for a in dir(file_obj) if not a.startswith('_')]
                    yield self.create_text_message(f"Error: File path could not be determined. Object type: {type(file_obj)}. Available attributes: {attrs}")
                    return

                # 4. Run the parser
                print(f"🚀 Parsing file: {file_path}")
                result = parser.parse(file_path)
                
                if not result or not result.text:
                    yield self.create_text_message("Warning: No content extracted.")
                    return
                    
                yield self.create_text_message(result.text)

            finally:
                # Cleanup temp file if created
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass

        except Exception as e:
            # Enhanced error message with environment details to debug isolation
            env_info = f"\n[DEBUG] PATH: {os.environ.get('PATH', 'N/A')}"
            env_info += f"\n[DEBUG] User: {os.environ.get('USER', 'N/A')}"
            env_info += f"\n[DEBUG] Files at /: {os.listdir('/')[:10]}..." # First 10 items
            
            # Check candidate paths again in the error message for direct feedback
            best_path = "/Users/serdalaslantas/.nvm/versions/node/v24.13.1/bin/liteparse"
            if os.path.exists(best_path):
                 env_info += f"\n[DEBUG] {best_path} exists but failed to execute."
            else:
                 env_info += f"\n[DEBUG] {best_path} does not exist in this environment."

            yield self.create_text_message(f"Parsing failed with error: {str(e)}{env_info}")