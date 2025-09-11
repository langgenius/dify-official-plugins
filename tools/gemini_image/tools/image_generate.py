import base64
import json
from typing import Any, Optional, Union
import logging
from google import genai
from google.cloud import aiplatform
from google.genai.types import GenerateContentConfig, Part
from google.oauth2 import service_account

from dify_plugin.file.file import File
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from collections.abc import Generator

class ImageGenerateTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        
        location = self.runtime.credentials["vertex_location"]
        service_account_info = (
            json.loads(base64.b64decode(service_account_key))
            if (service_account_key := self.runtime.credentials.get("vertex_service_account_key", ""))
            else None
        )
        project_id = self.runtime.credentials["vertex_project_id"]
        if service_account_info:
            service_accountSA = service_account.Credentials.from_service_account_info(service_account_info)
            aiplatform.init(credentials=service_accountSA, project=project_id, location=location, api_transport="rest")
        else:
            aiplatform.init(project=project_id, location=location, api_transport="rest")
        SCOPES = [
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/generative-language",
        ]
        credential = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        client = genai.Client(credentials=credential, project=project_id, location=location, vertexai=True)

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
            return
        model = tool_parameters.get("model", "gemini-2.5-flash-image-preview")
        images = tool_parameters.get("images")
        contents = None
        if images:
            contents = []
            if isinstance(images, list):
                for image in images:
                    if not isinstance(image, File):
                        yield self.create_text_message("Error: All input images must be valid files.")
                        return
                    try:
                        contents.append(Part.from_bytes(data=image.blob, mime_type=image.mime_type))
                    except Exception as e:
                        yield self.create_text_message(f"Error processing input image: {e}")
                        return
            else:
                if not isinstance(images, File):
                    yield self.create_text_message("Error: Input image must be a valid file.")
                    return
                try:
                    contents.append(Part.from_bytes(data=images.blob, mime_type=images.mime_type))
                except Exception as e:
                    yield self.create_text_message(f"Error processing input image: {e}")
                    return
            contents.append(prompt)
        else:
            contents = prompt

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=GenerateContentConfig(response_modalities=["TEXT", "IMAGE"], candidate_count=1),
            )
        except Exception as e:
            yield self.create_text_message(f"Error: {e}")
        messages = []
        for part in response.candidates[0].content.parts:
            if part.text:
                messages.append(self.create_text_message(part.text))
            if part.inline_data:
                messages.append(self.create_blob_message(blob=part.inline_data.data, meta={"mime_type": "image/png"}))
        for message in messages:
            yield message
