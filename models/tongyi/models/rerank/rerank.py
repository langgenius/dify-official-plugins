import base64
import os
from typing import Optional

import dashscope
import yaml
from dashscope.common.error import (
    AuthenticationError,
    InvalidParameter,
    RequestFailure,
    ServiceUnavailableError,
    UnsupportedHTTPMethod,
    UnsupportedModel,
)
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.entities.model.text_embedding import MultiModalContent, MultiModalContentType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.rerank_model import MultiModalRerankResult, RerankModel
from models._common import get_http_base_address
from ..constant import BURY_POINT_HEADER

vision_models: dict[str, bool] = {}


class GTERerankModel(RerankModel):
    """
    Model class for GTE rerank model.
    """

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
        Invoke rerank model

        :param model: model name
        :param credentials: model credentials
        :param query: search query
        :param docs: docs for reranking
        :param score_threshold: score threshold
        :param top_n: top n
        :param user: unique user id
        :return: rerank result
        """
        if len(docs) == 0:
            return RerankResult(model=model, docs=docs)
        http_base_address = get_http_base_address(credentials)
        response = dashscope.TextReRank.call(
            query=query,
            headers=BURY_POINT_HEADER,
            documents=docs,
            model=model,
            top_n=top_n,
            return_documents=True,
            api_key=credentials["dashscope_api_key"],
            base_address=http_base_address,
        )
        rerank_documents = []
        if not response.output:
            return RerankResult(model=model, docs=rerank_documents)
        for _, result in enumerate(response.output.results):
            document = result.get("document") or {}
            rerank_document = RerankDocument(
                index=result.index,
                score=result.relevance_score,
                text=document.get("text") or docs[result.index],
            )
            if score_threshold is not None:
                if result.relevance_score >= score_threshold:
                    rerank_documents.append(rerank_document)
            else:
                rerank_documents.append(rerank_document)
        return RerankResult(model=model, docs=rerank_documents)

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        query: MultiModalContent,
        docs: list[MultiModalContent],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> MultiModalRerankResult:
        if not self._is_vision_model(model):
            raise NotImplementedError(
                f"{self.__class__.__name__} does not implement `_invoke_multimodal` for model {model}."
            )
        if len(docs) == 0:
            return MultiModalRerankResult(model=model, docs=[])

        http_base_address = get_http_base_address(credentials)
        response = dashscope.TextReRank.call(
            query=self._to_dashscope_query(query),
            headers=BURY_POINT_HEADER,
            documents=[self._to_dashscope_document(doc) for doc in docs],
            model=model,
            top_n=top_n,
            return_documents=True,
            api_key=credentials["dashscope_api_key"],
            base_address=http_base_address,
        )

        rerank_documents = []
        if not response.output:
            return MultiModalRerankResult(model=model, docs=rerank_documents)

        for result in response.output.results:
            doc_content = docs[result.index].content
            rerank_document = RerankDocument(
                index=result.index,
                score=result.relevance_score,
                text=doc_content if isinstance(doc_content, str) else str(doc_content),
            )
            if score_threshold is None or result.relevance_score >= score_threshold:
                rerank_documents.append(rerank_document)

        return MultiModalRerankResult(model=model, docs=rerank_documents)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self.invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital city of the American state of Nevada. At the 2010 United States Census, Carson City had a population of 55,274.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that are a political division controlled by the United States. Its capital is Saipan.",
                ],
                score_threshold=0.8,
            )
        except Exception as ex:
            print(ex)
            raise CredentialsValidateFailedError(str(ex))

    @staticmethod
    def _is_vision_model(model: str) -> bool:
        if model not in vision_models:
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                yaml_file_path = os.path.join(current_dir, f"{model}.yaml")

                if os.path.exists(yaml_file_path):
                    with open(yaml_file_path, "r", encoding="utf-8") as f:
                        yaml_content = yaml.safe_load(f)

                    if (
                        yaml_content
                        and "features" in yaml_content
                        and isinstance(yaml_content["features"], list)
                        and "vision" in yaml_content["features"]
                    ):
                        vision_models[model] = True
                        return True
            except Exception:
                pass
            vision_models[model] = False
        return vision_models[model]

    @staticmethod
    def _detect_image_format(base64_str: str) -> str:
        try:
            if "," in base64_str:
                base64_str = base64_str.split(",", 1)[1]

            data = base64.b64decode(base64_str, validate=True)

            if data.startswith(b"\xFF\xD8\xFF"):
                return "jpeg"
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                return "png"
            if data.startswith(b"BM"):
                return "bmp"
            if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
                return "webp"
            return "unknown"
        except Exception:
            return "unknown"

    @classmethod
    def _to_dashscope_image(cls, content: str) -> str:
        image_format = cls._detect_image_format(content)
        if image_format not in ["jpeg", "png", "bmp", "webp"]:
            raise ValueError(f"Unsupported image format: {image_format}")
        return f"data:image/{image_format};base64,{content}"

    @classmethod
    def _to_dashscope_query(cls, query: MultiModalContent) -> dict:
        if query.content_type == MultiModalContentType.TEXT:
            return {"text": query.content}
        if query.content_type == MultiModalContentType.IMAGE:
            return {"image": cls._to_dashscope_image(query.content)}
        raise ValueError(f"Unsupported content type: {query.content_type}")

    @classmethod
    def _to_dashscope_document(cls, document: MultiModalContent) -> dict:
        if document.content_type == MultiModalContentType.TEXT:
            return {"text": document.content}
        if document.content_type == MultiModalContentType.IMAGE:
            return {"image": cls._to_dashscope_image(document.content)}
        raise ValueError(f"Unsupported content type: {document.content_type}")

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [RequestFailure],
            InvokeServerUnavailableError: [ServiceUnavailableError],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [AuthenticationError],
            InvokeBadRequestError: [InvalidParameter, UnsupportedModel, UnsupportedHTTPMethod],
        }
