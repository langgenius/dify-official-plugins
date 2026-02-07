from typing import Mapping, Optional, Union
import json
import re

from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    I18nObject,
    ModelFeature,
)
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult

from dify_plugin.interfaces.model.openai_compatible.text_embedding import (
    OAICompatEmbeddingModel,
)


class OpenAITextEmbeddingModel(OAICompatEmbeddingModel):
    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        credentials = credentials or {}
        entity = super().get_customizable_model_schema(model, credentials)

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_US=credentials["display_name"], zh_Hans=credentials["display_name"]
            )

        # Add vision feature if vision support is enabled
        vision_support = credentials.get("vision_support", "no_support")
        if vision_support == "support" and ModelFeature.VISION not in entity.features:
            entity.features.append(ModelFeature.VISION)

        return entity

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model with multimodal support

        Supports both text-only and multimodal (text + image) inputs.
        When vision_support is enabled, texts can contain JSON with "text" and "image" fields.

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed (can be JSON strings for multimodal)
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        # Check if vision support is enabled
        vision_support = credentials.get("vision_support", "no_support")

        # Process inputs - convert to multimodal format if needed
        processed_inputs = []
        for text in texts:
            processed = self._process_input(text, vision_support == "support")
            processed_inputs.append(processed)

        # Apply prefix
        prefix = self._get_prefix(credentials, input_type)
        if prefix:
            processed_inputs = self._add_prefix_to_inputs(processed_inputs, prefix)

        # Call parent with processed inputs
        return self._invoke_multimodal(model, credentials, processed_inputs, user)

    def _process_input(self, text: str, vision_enabled: bool) -> Union[str, list]:
        """
        Process input text, detecting and handling multimodal content.

        :param text: input text which may contain JSON with image data
        :param vision_enabled: whether vision support is enabled
        :return: processed content (str or list) for API
        """
        if not vision_enabled:
            return text

        # Try to parse as JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return self._format_multimodal_content(data)
        except json.JSONDecodeError:
            pass

        # Try to detect markdown image syntax: ![desc](url)
        if vision_enabled:
            content = self._extract_markdown_images(text)
            if content != text:
                return content

        # Try to detect plain image URLs
        if vision_enabled and self._is_image_url(text):
            return [{"type": "image_url", "image_url": {"url": text}}]

        return text

    def _format_multimodal_content(self, data: dict) -> Union[str, list]:
        """
        Format multimodal content dict to OpenAI API format.

        Expected format: {"text": "...", "image": "url_or_path"}
        """
        content = []

        # Add image if present
        if "image" in data and data["image"]:
            image_url = self._process_image_url(data["image"])
            if image_url:
                content.append({"type": "image_url", "image_url": {"url": image_url}})

        # Add text if present
        if "text" in data and data["text"]:
            content.append({"type": "text", "text": data["text"]})

        return content if content else data.get("text", "")

    def _process_image_url(self, image: str) -> str:
        """
        Process image URL or path.

        Supports:
        - HTTP/HTTPS URLs
        - Local file paths (converted to file://)
        - Base64 data URIs
        """
        if not image:
            return ""

        # Already a URL
        if image.startswith(("http://", "https://", "data:image")):
            return image

        # Local file path - convert to file://
        if image.startswith("file://"):
            return image

        # Assume it's a local file path
        return f"file://{image}"

    def _extract_markdown_images(self, text: str) -> Union[str, list]:
        """
        Extract markdown image syntax: ![description](url)

        :param text: text potentially containing markdown images
        :return: processed content
        """
        # Pattern to match markdown images
        pattern = r"!\[([^\]]*)\]\(([^\)]+)\)"

        matches = list(re.finditer(pattern, text))
        if not matches:
            return text

        content = []
        last_end = 0

        for match in matches:
            # Add text before image
            if match.start() > last_end:
                text_part = text[last_end : match.start()].strip()
                if text_part:
                    content.append({"type": "text", "text": text_part})

            # Add image
            image_url = match.group(2)
            content.append({"type": "image_url", "image_url": {"url": image_url}})

            last_end = match.end()

        # Add remaining text
        if last_end < len(text):
            text_part = text[last_end:].strip()
            if text_part:
                content.append({"type": "text", "text": text_part})

        return content

    def _is_image_url(self, text: str) -> bool:
        """Check if text is an image URL."""
        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")
        return text.startswith(("http://", "https://")) and any(
            text.lower().endswith(ext) for ext in image_extensions
        )

    def _add_prefix_to_inputs(self, inputs: list, prefix: str) -> list:
        """Add prefix to text inputs."""
        result = []
        for item in inputs:
            if isinstance(item, str):
                result.append(f"{prefix} {item}")
            elif isinstance(item, list):
                # It's a multimodal content list
                for content in item:
                    if content.get("type") == "text":
                        content["text"] = f"{prefix} {content['text']}"
                result.append(item)
            else:
                result.append(item)
        return result

    def _get_prefix(self, credentials: dict, input_type: EmbeddingInputType) -> str:
        if input_type == EmbeddingInputType.DOCUMENT:
            return credentials.get("document_prefix", "")

        if input_type == EmbeddingInputType.QUERY:
            return credentials.get("query_prefix", "")

        return ""

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        inputs: list,
        user: Optional[str] = None,
    ) -> TextEmbeddingResult:
        """
        Invoke embedding model with potentially multimodal inputs.

        This overrides the parent method to support multimodal content.
        """
        import requests
        from dify_plugin.errors.model import InvokeError, InvokeServerUnavailableError
        from dify_plugin.entities.model.text_embedding import EmbeddingUsage

        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        api_key = credentials.get("api_key", "")
        endpoint_model_name = credentials.get("endpoint_model_name", "") or model

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        embeddings = []
        total_tokens = 0

        try:
            for input_data in inputs:
                # Build payload
                if isinstance(input_data, list):
                    # Multimodal input
                    payload = {
                        "model": endpoint_model_name,
                        "input": input_data,
                        "encoding_format": credentials.get("encoding_format", "float"),
                    }
                else:
                    # Text-only input
                    payload = {
                        "model": endpoint_model_name,
                        "input": input_data,
                        "encoding_format": credentials.get("encoding_format", "float"),
                    }

                response = requests.post(
                    f"{endpoint_url}/embeddings",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()

                result = response.json()
                embedding = result["data"][0]["embedding"]
                tokens = result.get("usage", {}).get("prompt_tokens", 0)

                embeddings.append(embedding)
                total_tokens += tokens

            return TextEmbeddingResult(
                embeddings=embeddings,
                model=model,
                usage=EmbeddingUsage(tokens=total_tokens),
            )

        except requests.exceptions.RequestException as ex:
            raise InvokeServerUnavailableError(str(ex))
        except Exception as ex:
            raise InvokeError(str(ex))
