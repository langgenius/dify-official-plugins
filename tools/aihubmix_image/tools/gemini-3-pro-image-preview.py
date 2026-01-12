from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("openai package is required. Please install it with: pip install openai")


class Gemini3ProImagePreviewTool(Tool):
    BASE_URL = "https://aihubmix.com/v1"
    
    def create_image_info(self, base64_data: str, aspect_ratio: str, resolution: str) -> dict:
        return {
            "url": f"data:image/png;base64,{base64_data}",
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "format": "png"
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            aspect_ratio = tool_parameters.get("aspect_ratio", "1:1")
            resolution = tool_parameters.get("resolution", "4K")
            
            valid_ratios = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
            if aspect_ratio not in valid_ratios:
                raise InvokeError(f"Invalid aspect ratio. Must be one of: {', '.join(valid_ratios)}")
            
            valid_resolutions = ["1K", "2K", "4K"]
            if resolution not in valid_resolutions:
                raise InvokeError(f"Invalid resolution. Must be one of: {', '.join(valid_resolutions)}")
            
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            client = OpenAI(
                api_key=api_key,
                base_url=self.BASE_URL,
                timeout=240.0,  # 4 minutes timeout for 4K image generation
            )

            system_content = f"aspect_ratio={aspect_ratio}; resolution={resolution}"

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
                            image_info = self.create_image_info(image_data, aspect_ratio, resolution)
                            images.append(image_info)
            elif hasattr(message, 'content') and message.content:
                text_content = message.content
            
            if not images:
                raise InvokeError("No images were generated in the response")
            
            yield self.create_json_message({
                "success": True,
                "model": "gemini-3-pro-image-preview",
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "num_images": len(images),
                "images": images,
                "text_content": text_content
            })
                
        except Exception as e:
            raise InvokeError(f"Gemini 3 Pro Image Preview generation failed: {str(e)}")
