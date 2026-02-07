import json
import re
from typing import Mapping, Optional, Union, Any

from dify_plugin.entities.model import AIModelEntity, I18nObject, ModelFeature
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult, RerankUsage

from dify_plugin.interfaces.model.openai_compatible.rerank import OAICompatRerankModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeError,
    InvokeServerUnavailableError,
)
import requests


class OpenAIRerankModel(OAICompatRerankModel):
    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital city of the American state of Nevada. At the 2010 United States "
                    "Census, Carson City had a population of 55,274.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that "
                    "are a political division controlled by the United States. Its capital is Saipan.",
                    "Washington, D.C., formally the District of Columbia, is the capital city and federal district of "
                    "the United States. It is located on the east bank of the Potomac River.",
                ],
                score_threshold=0.8,
                top_n=3,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
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
        query: str,
        docs: list[str],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> RerankResult:
        """
        Invoke rerank model with multimodal support.

        Supports both text-only and multimodal (text + image) inputs.
        When vision_support is enabled, query and docs can contain JSON with "text" and "image" fields.

        :param model: model name
        :param credentials: model credentials
        :param query: query text (can be JSON with image for multimodal)
        :param docs: documents to rerank (can be JSON with images for multimodal)
        :param score_threshold: score threshold
        :param top_n: top n documents to return
        :param user: unique user id
        :return: rerank result
        """
        if not docs:
            return RerankResult(
                model=model,
                docs=[],
                usage=RerankUsage(total_tokens=0),
            )

        # Check if vision support is enabled
        vision_support = credentials.get("vision_support", "no_support")
        vision_enabled = vision_support == "support"

        # Process query and documents
        processed_query = self._process_input(query, vision_enabled)
        processed_docs = [self._process_input(doc, vision_enabled) for doc in docs]

        # Build API request
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        api_key = credentials.get("api_key", "")
        endpoint_model_name = credentials.get("endpoint_model_name", "") or model

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        # Build payload
        payload = {
            "model": endpoint_model_name,
            "query": processed_query,
            "documents": processed_docs,
            "top_n": top_n if top_n else len(docs),
            "return_documents": True,
        }

        if score_threshold is not None:
            payload["score_threshold"] = score_threshold

        try:
            response = requests.post(
                f"{endpoint_url}/rerank",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()

            result = response.json()

            # Parse rerank results
            rerank_docs = []
            for item in result.get("results", []):
                index = item.get("index", 0)
                score = item.get("relevance_score", 0.0)
                document = item.get("document", {})

                if index < len(docs):
                    rerank_docs.append(
                        RerankDocument(
                            index=index,
                            score=score,
                            text=document.get("text", docs[index]),
                        )
                    )

            # Sort by score (highest first)
            rerank_docs.sort(key=lambda x: x.score, reverse=True)

            # Apply top_n if specified
            if top_n:
                rerank_docs = rerank_docs[:top_n]

            # Apply score threshold
            if score_threshold is not None:
                rerank_docs = [
                    doc for doc in rerank_docs if doc.score >= score_threshold
                ]

            total_tokens = result.get("usage", {}).get("total_tokens", 0)

            return RerankResult(
                model=model,
                docs=rerank_docs,
                usage=RerankUsage(total_tokens=total_tokens),
            )

        except requests.exceptions.RequestException as ex:
            raise InvokeServerUnavailableError(str(ex))
        except Exception as ex:
            raise InvokeError(str(ex))

    def _process_input(self, text: str, vision_enabled: bool) -> Union[str, dict, list]:
        """
        Process input text, detecting and handling multimodal content.

        :param text: input text which may contain JSON with image data
        :param vision_enabled: whether vision support is enabled
        :return: processed content (str, dict, or list) for API
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
        content = self._extract_markdown_images(text)
        if content != text:
            return content

        # Try to detect plain image URLs
        if self._is_image_url(text):
            return {"type": "image_url", "image_url": {"url": text}}

        return text

    def _format_multimodal_content(self, data: dict) -> Union[str, dict, list]:
        """
        Format multimodal content dict to API format.

        Expected formats:
        - {"text": "...", "image": "url_or_path"}
        - {"image": "url_or_path"}
        - {"text": "..."}
        """
        text = data.get("text", "")
        image = data.get("image", "")

        if image and text:
            # Both text and image
            image_url = self._process_image_url(image)
            return {
                "type": "multimodal",
                "text": text,
                "images": [image_url] if image_url else [],
            }
        elif image:
            # Only image
            image_url = self._process_image_url(image)
            return (
                {"type": "image_url", "image_url": {"url": image_url}}
                if image_url
                else ""
            )
        else:
            # Only text
            return text

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

        # Already file://
        if image.startswith("file://"):
            return image

        # Assume it's a local file path
        import os

        abs_path = os.path.abspath(image)
        return f"file://{abs_path}"

    def _extract_markdown_images(self, text: str) -> Union[str, list]:
        """
        Extract markdown image syntax: ![description](url)

        :param text: text potentially containing markdown images
        :return: processed content
        """
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
