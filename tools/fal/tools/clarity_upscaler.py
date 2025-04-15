import os
from typing import Any, Generator
import fal_client
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from dify_plugin.file.file import File


class ClarityUpscalerTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        image_file: File | None = tool_parameters.get("image_file")
        image_url: str | None = tool_parameters.get("image_url")
        
        if not image_file and not image_url:
            yield self.create_text_message("No image file or URL provided")
            return
        
        prompt = tool_parameters.get("prompt", "masterpiece, best quality, highres")
        upscale_factor = tool_parameters.get("upscale_factor", 2)
        negative_prompt = tool_parameters.get("negative_prompt", "(worst quality, low quality, normal quality:2)")
        creativity = tool_parameters.get("creativity", 0.35)
        resemblance = tool_parameters.get("resemblance", 0.6)
        guidance_scale = tool_parameters.get("guidance_scale", 4)
        num_inference_steps = tool_parameters.get("num_inference_steps", 18)
        seed = tool_parameters.get("seed")
        enable_safety_checker = tool_parameters.get("enable_safety_checker", True)

        api_key = self.runtime.credentials["fal_api_key"]
        os.environ["FAL_KEY"] = api_key
        
        # If image file is provided, upload it first
        if image_file:
            image_binary = image_file.blob
            mime_type = image_file.mime_type
            try:
                image_url = fal_client.upload(image_binary, mime_type or "image/jpeg")
            except Exception as e:
                yield self.create_text_message(f"Error uploading image file: {str(e)}")
                return
        
        arguments = {
            "image_url": image_url,
            "prompt": prompt,
            "upscale_factor": upscale_factor,
            "negative_prompt": negative_prompt,
            "creativity": creativity,
            "resemblance": resemblance,
            "guidance_scale": guidance_scale,
            "num_inference_steps": num_inference_steps,
            "enable_safety_checker": enable_safety_checker
        }
        
        # Add seed if provided
        if seed is not None:
            arguments["seed"] = seed
        
        try:
            result = fal_client.subscribe("fal-ai/clarity-upscaler", arguments=arguments, with_logs=False)
            json_message = self.create_json_message(result)
            
            # Create a more user-friendly message with the result image
            if "image" in result and "url" in result["image"]:
                # Create an image message directly with the URL
                image_url = result["image"]["url"]
                image_message = self.create_image_message(image_url=image_url)
                yield from [json_message, image_message]
            else:
                text = "Image upscaled successfully, but no URL was returned."
                text_message = self.create_text_message(text)
                yield from [json_message, text_message]
        except Exception as e:
            yield self.create_text_message(f"Error upscaling image: {str(e)}")
