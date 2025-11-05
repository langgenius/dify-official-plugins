import json
import logging
import time
from typing import Optional, List

from dify_plugin import TextEmbeddingModel

from dify_plugin.entities.model import EmbeddingInputType, ModelType, PriceType
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from tencentcloud.common import credential
from tencentcloud.common.exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.es.v20250101 import es_client, models
from dify_plugin.entities.model.text_embedding import (
    TextEmbeddingResult, EmbeddingUsage,
)

logger = logging.getLogger(__name__)


class AiSearchTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for aisearch text embedding model.
    """
    model_type = ModelType.TEXT_EMBEDDING
    DEFAULT_MODEL_NAME = "bge-base-zh-v1.5"
    API_ENDPOINT = "es.tencentcloudapi.com"
    API_VERSION = "2025-01-01"
    DEFAULT_API_REGION = "ap-beijing"

    # Supported regions list
    SUPPORTED_REGIONS = [
        "ap-beijing", "ap-singapore"
    ]

    # Supported models list
    SUPPORTED_MODELS = [
        "bge-base-zh-v1.5",
        "Conan-embedding-v1",
        "bge-m3",
        "KaLM-embedding-multilingual-mini-v1",
        "Qwen3-Embedding-0.6B"
    ]

    def _invoke(
            self,
            model: str,
            credentials: dict,
            texts: List[str],
            user: Optional[str] = None,
            input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :param user: unique user id
        :param input_type: embedding input type
        :return: embeddings result
        """
        self.started_at = time.perf_counter()

        try:
            # 1. Parameter validation
            if not texts or not isinstance(texts, list):
                raise InvokeError("Input texts must be a non-empty list")

            # 2. Validate model support
            if model not in self.SUPPORTED_MODELS:
                raise CredentialsValidateFailedError(f"Model {model} is not supported")

            # 3. Initialize client
            client = self._setup_es_client(credentials)

            # 4. Build request parameters
            params = {
                "ModelName": model or self.DEFAULT_MODEL_NAME,
                "Texts": texts
            }

            logger.debug(f"Request params: {json.dumps(params, ensure_ascii=False)}")

            # 5. Create request object and call API
            req = models.GetTextEmbeddingRequest()
            req.from_json_string(json.dumps(params))

            response = client.GetTextEmbedding(req)
            logger.debug("TencentCloud ES API response received successfully")

            # 6. Process response and extract embeddings and token usage
            embeddings, total_tokens = self._process_response(response, texts)

            # 7. Calculate usage with actual token count using framework pricing
            usage = self._create_usage(model, credentials, total_tokens)

            result = TextEmbeddingResult(
                model=model,
                embeddings=embeddings,
                usage=usage,
            )

            logger.debug("Text embedding completed successfully")
            return result

        except TencentCloudSDKException as e:
            logger.error(f"TencentCloud SDK Error: {str(e)}", exc_info=True)
            raise InvokeError(f"API request failed: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise InvokeError(f"Processing failed: {str(e)}")

    def get_num_tokens(self, model: str, credentials: dict, texts: List[str]) -> List[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return: list of token counts
        """
        tokens = []
        for text in texts:
            tokens.append(self._get_num_tokens_by_gpt2(text))
        return tokens

    def _setup_es_client(self, credentials: dict) -> es_client.EsClient:
        """
        Standardized Tencent Cloud client initialization using es_client

        :param credentials: credential information
        :return: EsClient instance
        """
        try:
            # Validate credential fields
            secret_id = credentials.get("secret_id")
            secret_key = credentials.get("secret_key")

            if not secret_id or not secret_key:
                raise CredentialsValidateFailedError("Missing required credentials: secret_id and secret_key")

            cred = credential.Credential(secret_id, secret_key)

            http_profile = HttpProfile()
            http_profile.endpoint = self.API_ENDPOINT
            http_profile.reqTimeout = 30

            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile

            # Get region from credentials or use default
            region = credentials.get("region", self.DEFAULT_API_REGION)

            return es_client.EsClient(cred, region, client_profile)
        except KeyError as e:
            raise CredentialsValidateFailedError(f"Missing credential field: {str(e)}")
        except Exception as e:
            raise CredentialsValidateFailedError(f"Client setup failed: {str(e)}")

    def _process_response(self, response: object, texts: List[str]) -> tuple[List[List[float]], int]:
        """
        Process API response and extract embedding data and token usage

        :param response: API response
        :param texts: original text list
        :return: tuple of (embedding list, total_tokens)
        """
        if not response:
            logger.error(f"Empty API response")
            raise InvokeError("Empty API response")

        # Extract response data
        if hasattr(response, 'Response'):
            resp_data = response.Response
        else:
            resp_data = response

        # Check error code
        if hasattr(resp_data, 'Error') and resp_data.Error:
            error_msg = getattr(resp_data.Error, 'Message', 'Unknown error')
            logger.error(f"API returned error: {error_msg}")
            raise InvokeError(f"API error: {error_msg}")

        if not hasattr(resp_data, 'Data') or not resp_data.Data:
            logger.error(f"Missing or invalid Data field in response: {resp_data}")
            raise InvokeError("API response missing required 'Data' field")

        if len(resp_data.Data) != len(texts):
            logger.error(f"Response data count mismatch: expected {len(texts)}, got {len(resp_data.Data)}")
            raise InvokeError("Response data count mismatch")

        # Extract token usage from response
        total_tokens = 0
        if hasattr(resp_data, 'Usage') and resp_data.Usage:
            usage_data = resp_data.Usage
            if hasattr(usage_data, 'TotalTokens'):
                total_tokens = int(usage_data.TotalTokens)
                logger.debug(f"Extracted total tokens from response: {total_tokens}")
            else:
                logger.warning("Usage data found but TotalTokens field missing, falling back to text count")
                total_tokens = len(texts)
        else:
            logger.warning("Usage data not found in response, falling back to text count")
            total_tokens = len(texts)

        embeddings = []
        for i, item in enumerate(resp_data.Data):
            embedding_data = getattr(item, 'Embedding', None)
            if embedding_data is None or not hasattr(embedding_data, '__iter__'):
                logger.error(f"Invalid embedding data at index {i}: {item}")
                raise InvokeError(f"Invalid embedding data format at index {i}")

            # Ensure embedding data is valid float list
            try:
                embedding = [float(x) for x in embedding_data]
                embeddings.append(embedding)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid embedding values at index {i}: {e}")
                raise InvokeError(f"Invalid embedding values at index {i}")

        return embeddings, total_tokens

    def _create_usage(self, model: str, credentials: dict, total_tokens: int) -> EmbeddingUsage:
        """
        Create usage statistics with actual token count using framework pricing

        :param model: model name
        :param credentials: model credentials
        :param total_tokens: actual token count from API response
        :return: EmbeddingUsage instance
        """
        latency = time.perf_counter() - self.started_at

        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=total_tokens
        )

        return EmbeddingUsage(
            tokens=total_tokens,
            total_tokens=total_tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=float(latency)
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return: None
        """
        try:
            # 1. Validate required fields
            if not credentials.get("secret_id") or not credentials.get("secret_key"):
                raise CredentialsValidateFailedError("Missing required credentials: secret_id and secret_key")

            # 2. Initialize client
            client = self._setup_es_client(credentials)

            # 3. Test API call
            test_params = {
                "ModelName": model or self.DEFAULT_MODEL_NAME,
                "Texts": ["credentials validation test"]
            }

            req = models.GetTextEmbeddingRequest()
            req.from_json_string(json.dumps(test_params))

            response = client.GetTextEmbedding(req)

            # 4. Check response
            if not response:
                raise CredentialsValidateFailedError("TencentCloud ES API returned empty response")

            # Check if response has Error field
            if hasattr(response, 'Error') and response.Error:
                error_msg = getattr(response.Error, 'Message', 'Unknown error')
                raise CredentialsValidateFailedError(f"API test failed: {error_msg}")

            logger.info("Credentials validation successful")

        except TencentCloudSDKException as e:
            raise CredentialsValidateFailedError(f"API authentication failed: {e.message}")
        except CredentialsValidateFailedError:
            raise
        except Exception as e:
            raise CredentialsValidateFailedError(f"Validation error: {str(e)}")

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], List[type[Exception]]]:
        """
        Map model invoke error to unified error

        :return: Invoke error mapping
        """
        return {InvokeError: [TencentCloudSDKException]}
