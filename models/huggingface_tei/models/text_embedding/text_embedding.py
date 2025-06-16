import time
from typing import Optional
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    PriceType,
)
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    TextEmbeddingResult,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel
from models.helper import TeiHelper

DEFAULT_MAX_RETRIES = 3
DEFAULT_INVOKE_TIMEOUT = 60


class HuggingfaceTeiTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for Text Embedding Inference text embedding model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model

        credentials should be like:
        {
            'server_url': 'server url',
            'model_uid': 'model uid',
        }

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        server_url = credentials["server_url"]
        server_url = server_url.removesuffix("/")
        max_retries = int(credentials.get("max_retries") or DEFAULT_MAX_RETRIES)
        invoke_timeout = int(credentials.get("invoke_timeout") or DEFAULT_INVOKE_TIMEOUT)
        headers = {"Content-Type": "application/json"}
        api_key = credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)
        inputs = []
        indices = []
        used_tokens = 0
        
        # Use GPT2 tokenizer instead of server's /tokenize endpoint
        for i, text in enumerate(texts):
            num_tokens = self._get_num_tokens_by_gpt2(text)
            if num_tokens >= context_size:
                # If text is too long, truncate it based on character length ratio
                cutoff = int(len(text) * (context_size / num_tokens))
                inputs.append(text[0:cutoff])
            else:
                inputs.append(text)
            indices += [i]
            used_tokens += num_tokens
            
        batched_embeddings = []
        _iter = range(0, len(inputs), max_chunks)
        try:
            for i in _iter:
                iter_texts = inputs[i : i + max_chunks]
                results = TeiHelper.invoke_embeddings(server_url, iter_texts, headers, invoke_timeout, max_retries)
                embeddings = results["data"]
                embeddings = [embedding["embedding"] for embedding in embeddings]
                batched_embeddings.extend(embeddings)
        except RuntimeError as e:
            raise InvokeServerUnavailableError(str(e))
        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=used_tokens
        )
        result = TextEmbeddingResult(
            model=model, embeddings=batched_embeddings, usage=usage
        )
        return result

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """
        Get number of tokens for given prompt messages using GPT2 tokenizer

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return: list of token counts
        """
        tokens = []
        for text in texts:
            tokens.append(self._get_num_tokens_by_gpt2(text))
        return tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            server_url = credentials["server_url"]
            headers = {"Content-Type": "application/json"}
            api_key = credentials.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            extra_args = TeiHelper.get_tei_extra_parameter(server_url, model, headers)
            print(extra_args)
            if extra_args.model_type != "embedding":
                raise CredentialsValidateFailedError(
                    "Current model is not a embedding model"
                )
            credentials["context_size"] = extra_args.max_input_length
            credentials["max_chunks"] = extra_args.max_client_batch_size
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [KeyError],
        }

    def _calc_response_usage(
        self, model: str, credentials: dict, tokens: int
    ) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )
        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - self.started_at,
        )
        return usage

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TEXT_EMBEDDING,
            model_properties={
                ModelPropertyKey.MAX_CHUNKS: int(credentials.get("max_chunks", 1)),
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 512)
                ),
            },
            parameter_rules=[],
        )
        return entity
