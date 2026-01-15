import json
import base64
from collections.abc import Generator
from typing import Any, Dict, List
from openai import OpenAI

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GptImageEditTool(Tool):
    """
    GPT Image Edit Tool
    Uses OpenAI's image editing API through AiHubMix service
    
    Supports multiple input formats:
    - HTTP/HTTPS URLs
    - Data URLs (base64 encoded)
    - Dify file transfer variables
    - Base64 encoded strings
    """
    
    def create_image_info(self, base64_data: str, size: str) -> dict:
        mime_type = "image/png"
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "size": size
        }
    
    def _process_image_input(self, image_input: Any) -> str:
        """
        Process image input from various sources and return a valid URL for API
        
        Args:
            image_input: Can be URL string, data URL, base64 string, or Dify file object
            
        Returns:
            Valid image URL or data URL for the API
        """
        if not image_input:
            raise InvokeError("Input image is required")
        
        image_str = str(image_input).strip()
        
        # Check if it's a Dify file transfer variable or file object
        if isinstance(image_input, dict):
            # Dify file variable format
            if "type" in image_input and image_input["type"] == "image":
                # Extract URL from file object
                if "transfer_method" in image_input:
                    if image_input["transfer_method"] == "remote_url":
                        return image_input.get("url", "")
                    elif image_input["transfer_method"] == "local_file":
                        # For local files, we need to use base64
                        if "base64_data" in image_input:
                            return f"data:image/png;base64,{image_input['base64_data']}"
                elif "url" in image_input:
                    return image_input["url"]
                elif "base64_data" in image_input:
                    return f"data:image/png;base64,{image_input['base64_data']}"
            # Fallback for other dict formats
            image_str = str(image_input)
        
        # Check if text contains URL (for workflow connections where user connected text output)
        # This handles cases where user connected 'text' output instead of 'files' output
        import re
        url_pattern = r'https?://[^\s\)]+'
        urls = re.findall(url_pattern, image_str)
        if urls:
            # Return the first URL found in the text
            return urls[0]
        
        # Already a valid URL format
        if image_str.startswith('http://') or image_str.startswith('https://'):
            return image_str
        
        # Data URL format
        if image_str.startswith('data:image/'):
            return image_str
        
        # Base64 encoded image (with or without prefix)
        if image_str.startswith('iVBORw0KGgo') or '/' in image_str or '=' in image_str:
            # Likely base64 encoded
            try:
                # Try to decode to verify it's valid base64
                base64.b64decode(image_str)
                return f"data:image/png;base64,{image_str}"
            except:
                pass
        
        # If none of the above, return as-is (will be processed by the existing logic)
        return image_str
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for GPT Image Edit
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Edit prompt is required")
            
            # Process image input from various sources
            image_input = tool_parameters.get("image", "")
            image_file = self._process_image_input(image_input)
            if not image_file:
                raise InvokeError("Input image is required")
            
            model = tool_parameters.get("model", "gpt-image-1")
            size = tool_parameters.get("size", "1024x1024")
            n = int(tool_parameters.get("n", 1))
            
            # Validate parameters
            if n < 1 or n > 4:
                raise InvokeError("Number of images must be between 1 and 4")
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            yield self.create_text_message(f"Editing image with GPT Image Edit using model: {model}...")
            
            # Initialize OpenAI client with AiHubMix endpoint
            client = OpenAI(
                api_key=api_key,
                base_url="https://aihubmix.com/v1",
                timeout=180  # Increase timeout to 180 seconds for image editing
            )
            
            # Handle image input - convert to file-like object for OpenAI client
            image_data = None
            
            if image_file.startswith('data:image'):
                # Extract base64 data from data URL and decode
                image_data = base64.b64decode(image_file.split(',')[1])
            elif image_file.startswith('http'):
                # Download image from URL
                import requests
                try:
                    response = requests.get(image_file, timeout=30)
                    if response.status_code == 200:
                        image_data = response.content
                    else:
                        raise InvokeError(f"Failed to download image from URL: {image_file}")
                except Exception as e:
                    raise InvokeError(f"Error downloading image from URL: {str(e)}")
            else:
                # Assume it's a file path or base64 string
                try:
                    if image_file.startswith('iVBORw0KGgo') or len(image_file) > 1000:
                        # Likely base64 image data
                        image_data = base64.b64decode(image_file)
                    else:
                        # Try to read as file
                        with open(image_file, 'rb') as f:
                            image_data = f.read()
                except Exception as e:
                    raise InvokeError(f"Error processing image input: {str(e)}")
            
            if not image_data:
                raise InvokeError("Failed to process image input")
            
            # Save image data to temporary file for OpenAI client
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_file.write(image_data)
                temp_image_path = temp_file.name
            
            try:
                # Use OpenAI client to edit image with retry logic
                max_retries = 2
                result = None
                
                for attempt in range(max_retries):
                    try:
                        yield self.create_text_message(f"Processing image edit (attempt {attempt + 1}/{max_retries})...")
                        
                        result = client.images.edit(
                            model=model,
                            image=open(temp_image_path, "rb"),
                            prompt=prompt,
                            n=n,
                            size=size
                        )
                        break  # Success, exit retry loop
                        
                    except Exception as retry_error:
                        if attempt == max_retries - 1:
                            raise retry_error  # Last attempt, re-raise the error
                        
                        yield self.create_text_message(f"Attempt {attempt + 1} failed, retrying... Error: {str(retry_error)}")
                        continue
                
                if not result:
                    raise InvokeError("Failed to edit image after multiple attempts")
                
                # Extract image data from response
                images = []
                for item in result.data:
                    if hasattr(item, 'url') and item.url:
                        images.append({"url": item.url})
                    elif hasattr(item, 'b64_json') and item.b64_json:
                        images.append({"b64_json": item.b64_json})
                
                if not images:
                    raise InvokeError("No edited images were generated")
                
                # Process images - return as blobs for base64 data, or display URLs
                for idx, img in enumerate(images):
                    if "b64_json" in img:
                        # Decode base64 and return as blob
                        base64_data = img["b64_json"]
                        image_bytes = base64.b64decode(base64_data)
                        filename = f"gpt_image_edit_{idx + 1}.png"
                        mime_type = "image/png"
                        yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
                    elif "url" in img:
                        # For URL responses, create image message
                        yield self.create_image_message(img["url"])
                
                # Return results as JSON
                yield self.create_json_message({
                    "success": True,
                    "model": model,
                    "prompt": prompt,
                    "size": size,
                    "num_images": len(images),
                    "images": images
                })
                
                # Also create text message with image URLs
                image_urls = "\n".join([img['url'] for img in images if 'url' in img])
                if image_urls:
                    yield self.create_text_message(image_urls)
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_image_path)
                except:
                    pass
                
        except Exception as e:
            # Provide more detailed error information
            error_msg = str(e)
            
            # Handle specific timeout errors
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                error_msg = f"Image editing timed out. This may be due to high server load or complex editing requests. Please try again with a simpler prompt or smaller image. Original error: {error_msg}"
            
            # Handle connection errors
            elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                error_msg = f"Network connection error during image editing. Please check your internet connection and try again. Original error: {error_msg}"
            
            # Handle API errors
            elif "401" in error_msg or "unauthorized" in error_msg.lower():
                error_msg = f"API authentication failed. Please check your API key. Original error: {error_msg}"
            
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                error_msg = f"API rate limit exceeded. Please wait a moment and try again. Original error: {error_msg}"
            
            elif "500" in error_msg or "502" in error_msg or "503" in error_msg or "504" in error_msg:
                error_msg = f"Server error occurred. The service may be temporarily unavailable. Please try again later. Original error: {error_msg}"
            
            else:
                error_msg = f"GPT Image Edit failed: {error_msg}"
            
            raise InvokeError(error_msg)
