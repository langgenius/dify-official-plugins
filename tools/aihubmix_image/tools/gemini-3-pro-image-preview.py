from collections.abc import Generator
from typing import Any
import base64
import io

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("openai package is required. Please install it with: pip install openai")


class Gemini3ProImagePreviewTool(Tool):
    BASE_URL = "https://aihubmix.com/v1"
    
    def create_image_info(self, base64_data: str, aspect_ratio: str, resolution: str, image_format: str = "png") -> dict:
        mime_type = {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp"
        }.get(image_format, "image/png")
        
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "format": image_format
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            aspect_ratio = tool_parameters.get("aspect_ratio", "1:1")
            resolution = tool_parameters.get("resolution", "4K")
            image_format = tool_parameters.get("image_format", "png")
            
            valid_ratios = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
            if aspect_ratio not in valid_ratios:
                raise InvokeError(f"Invalid aspect ratio. Must be one of: {', '.join(valid_ratios)}")
            
            valid_resolutions = ["1K", "2K", "4K"]
            if resolution not in valid_resolutions:
                raise InvokeError(f"Invalid resolution. Must be one of: {', '.join(valid_resolutions)}")
            
            valid_formats = ["png", "jpeg", "webp"]
            if image_format not in valid_formats:
                raise InvokeError(f"Invalid image format. Must be one of: {', '.join(valid_formats)}")
            
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            client = OpenAI(
                api_key=api_key,
                base_url=self.BASE_URL,
                timeout=240.0,  # 4 minutes timeout for 4K image generation
            )

            system_content = f"aspect_ratio={aspect_ratio}; resolution={resolution}; format={image_format}"

            response = client.chat.completions.create(
                model="gemini-3-pro-image-preview",
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": [{"type": "text", "text": prompt}]},
                ],
                modalities=["text", "image"],
            )
            
            if not response.choices or not response.choices[0].message:
                raise InvokeError("No valid response received from Gemini 3 Pro Image Preview")
            
            message = response.choices[0].message
            images = []
            text_content = ""
            
            if hasattr(message, 'multi_mod_content') and message.multi_mod_content:
                for part in message.multi_mod_content:
                    if isinstance(part, dict):
                        if "text" in part:
                            text_content += part["text"]
                        if "inline_data" in part and "data" in part["inline_data"]:
                            image_data = part["inline_data"]["data"]
                            image_info = self.create_image_info(image_data, aspect_ratio, resolution, image_format)
                            images.append(image_info)
            elif hasattr(message, 'content') and message.content:
                text_content = message.content
            
            if not images:
                raise InvokeError("No images were generated in the response")
            
            # Return image files as blobs
            for idx, image_info in enumerate(images):
                base64_data = image_info["url"].split(",")[1]
                image_bytes = base64.b64decode(base64_data)
                
                file_extension = image_format if image_format != "jpeg" else "jpg"
                filename = f"gemini_3_pro_image_{idx + 1}.{file_extension}"
                
                mime_type = {
                    "png": "image/png",
                    "jpeg": "image/jpeg",
                    "webp": "image/webp"
                }.get(image_format, "image/png")
                
                yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
            
            # Also return metadata as JSON
            yield self.create_json_message({
                "success": True,
                "model": "gemini-3-pro-image-preview",
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "image_format": image_format,
                "num_images": len(images),
                "text_content": text_content
            })
                
        except Exception as e:
            raise InvokeError(f"Gemini 3 Pro Image Preview generation failed: {str(e)}")
