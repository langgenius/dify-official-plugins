import json
import math

from dify_plugin import OAICompatEmbeddingModel
from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType, ModelFeature
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
    MultiModalEmbeddingResult,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
)

from models.multimodal import api_base_url, content_part, post_json, require_vision


class GPUStackTextEmbeddingModel(OAICompatEmbeddingModel):
    """
    Model class for GPUStack text embedding model.
    """

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        if credentials.get("vision_support") == "support":
            documents = [
                MultiModalContent(content=text, content_type=MultiModalContentType.TEXT)
                for text in texts
            ]
            return self._embed_with_chat_template(model, credentials, documents, user)
        compatible_credentials = self._get_compatible_credentials(credentials)
        return super()._invoke(model, compatible_credentials, texts, user, input_type)

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        documents: list[MultiModalContent],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> MultiModalEmbeddingResult:
        require_vision(credentials)
        result = self._embed_with_chat_template(model, credentials, documents, user)
        return MultiModalEmbeddingResult(**result.model_dump())

    def _embed_with_chat_template(
        self,
        model: str,
        credentials: dict,
        documents: list[MultiModalContent],
        user: str | None,
    ) -> TextEmbeddingResult:
        """Use the chat-embeddings protocol for text and image inputs.

        Each typed input is a separate sample and yields one vector. In
        particular, multiple documents must not become one chat conversation.
        Model-specific formatting belongs to the serving template. Optional
        settings are applied equally to indexing and query requests.
        """
        parts = [content_part(document) for document in documents]
        template_options = self._chat_template_options(credentials)
        system_prompt = credentials.get("embedding_system_prompt") or ""
        if not isinstance(system_prompt, str):
            raise InvokeBadRequestError("Embedding system prompt must be text")
        embeddings = []
        tokens = 0
        dimension = None
        for part in parts:
            messages = []
            if system_prompt.strip():
                messages.append(
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": system_prompt}],
                    }
                )
            messages.append({"role": "user", "content": [part]})
            if template_options.get("continue_final_message"):
                messages.append(
                    {"role": "assistant", "content": [{"type": "text", "text": ""}]}
                )
            payload = {
                "model": credentials.get("endpoint_model_name") or model,
                "messages": messages,
                "encoding_format": "float",
                **template_options,
            }
            if user:
                payload["user"] = user
            result = post_json(
                api_base_url(credentials) + "/embeddings", credentials, payload
            )
            data = result.get("data")
            if (
                not isinstance(data, list)
                or len(data) != 1
                or not isinstance(data[0], dict)
            ):
                raise InvokeError("GPUStack must return one embedding per input")
            vector = data[0].get("embedding")
            if (
                data[0].get("index", 0) != 0
                or not isinstance(vector, list)
                or not vector
            ):
                raise InvokeError("GPUStack returned an invalid embedding")
            if not all(
                type(value) in (float, int) and math.isfinite(value) for value in vector
            ):
                raise InvokeError("GPUStack returned non-finite embedding values")
            if not any(vector):
                raise InvokeError("GPUStack returned a zero embedding")
            if dimension is not None and len(vector) != dimension:
                raise InvokeError("GPUStack returned inconsistent embedding dimensions")
            dimension = len(vector)
            embeddings.append(vector)
            usage = result.get("usage") or {}
            if not isinstance(usage, dict):
                raise InvokeError("GPUStack returned invalid embedding usage")
            used_tokens = usage.get("total_tokens")
            if used_tokens is None:
                used_tokens = usage.get("prompt_tokens")
            if used_tokens is None:
                used_tokens = 0
            if type(used_tokens) is not int or used_tokens < 0:
                raise InvokeError("GPUStack returned invalid token usage")
            tokens += used_tokens
        return TextEmbeddingResult(
            model=model,
            embeddings=embeddings,
            usage=self._calc_response_usage(model, credentials, tokens),
        )

    @staticmethod
    def _chat_template_options(credentials: dict) -> dict[str, bool]:
        """Validate optional template flags without selecting a model-specific preset."""
        raw = credentials.get("embedding_chat_template_options") or ""
        if not isinstance(raw, str):
            raise InvokeBadRequestError(
                "Embedding template options must be a JSON object string"
            )
        try:
            options = json.loads(raw.strip() or "{}")
        except ValueError:
            raise InvokeBadRequestError(
                "Embedding template options must be valid JSON"
            ) from None
        allowed = {
            "add_generation_prompt",
            "continue_final_message",
            "add_special_tokens",
        }
        if not isinstance(options, dict) or any(key not in allowed for key in options):
            raise InvokeBadRequestError(
                "Supported template options: add_generation_prompt, continue_final_message, add_special_tokens"
            )
        if any(type(value) is not bool for value in options.values()):
            raise InvokeBadRequestError(
                "Embedding template option values must be boolean"
            )
        if options.get("continue_final_message") and options.get(
            "add_generation_prompt"
        ):
            raise InvokeBadRequestError(
                "Continuation and generation prompts cannot both be enabled"
            )
        return options

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)
        if credentials.get("vision_support") == "support":
            entity.features = list(entity.features or [])
            if ModelFeature.VISION not in entity.features:
                entity.features.append(ModelFeature.VISION)
        return entity

    def validate_credentials(self, model: str, credentials: dict) -> None:
        if credentials.get("vision_support") == "support":
            try:
                self.invoke(model, credentials, ["ping"])
            except InvokeError as error:
                raise CredentialsValidateFailedError(
                    "GPUStack chat embedding validation failed"
                ) from error
            return
        compatible_credentials = self._get_compatible_credentials(credentials)
        super().validate_credentials(model, compatible_credentials)

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        credentials = credentials.copy()
        credentials["endpoint_url"] = api_base_url(credentials)
        if not credentials.get("endpoint_model_name"):
            credentials.pop("endpoint_model_name", None)
        return credentials
