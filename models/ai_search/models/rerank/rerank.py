import json
import logging
import time
from typing import Optional, List

from dify_plugin.entities.model import PriceType
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeError,
)
from dify_plugin.interfaces.model.rerank_model import RerankModel
from tencentcloud.common import credential
from tencentcloud.common.exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.es.v20250101 import es_client, models

logger = logging.getLogger(__name__)


class AiSearchRerankModel(RerankModel):
    """
    Tencent Cloud Atomic Service Rerank Model Plugin
    """

    # Configuration constants
    API_ENDPOINT = "es.tencentcloudapi.com"
    API_VERSION = "2025-01-01"
    DEFAULT_API_REGION = "ap-beijing"
    DEFAULT_TOP_N = 10
    DEFAULT_SCORE_THRESHOLD = 0.0

    # Supported regions list
    SUPPORTED_REGIONS = [
        "ap-beijing", "ap-singapore"
    ]

    # Supported models list
    SUPPORTED_MODELS = [
        "bge-reranker-large",
        "bge-reranker-v2-m3"
    ]

    def _invoke(
            self,
            model: str,
            credentials: dict,
            query: str,
            docs: List[str],
            score_threshold: Optional[float] = None,
            top_n: Optional[int] = None,
            user: Optional[str] = None,
    ) -> RerankResult:
        """
        Invoke Tencent Cloud Rerank service

        :param model: Model name
        :param credentials: Authentication credentials
        :param query: Query text
        :param docs: Documents to be reranked
        :param score_threshold: Score threshold (optional)
        :param top_n: Return top N results (optional)
        :param user: User ID (optional)
        :return: Rerank result
        """
        self.started_at = time.perf_counter()

        try:
            # 1. Parameter validation
            self._validate_input_params(query, docs)

            # 2. Handle empty documents case
            if not docs:
                logger.warning("Empty documents list provided")
                return RerankResult(model=model, docs=[])

            # 3. Validate model support
            if model not in self.SUPPORTED_MODELS:
                raise CredentialsValidateFailedError(f"Model {model} is not supported")

            # 4. Initialize client
            client = self._setup_es_client(credentials)

            # 5. Build request parameters
            params = self._build_request_params(model, query, docs, top_n)
            logger.debug(f"Request params: {json.dumps(params, ensure_ascii=False)}")

            # 6. Create request object and call API
            req = models.RunRerankRequest()
            req.from_json_string(json.dumps(params))

            response = client.RunRerank(req)
            logger.debug("TencentCloud ES API response received successfully")

            # 7. Process response and extract token usage
            rerank_documents, total_tokens = self._process_response(
                response, docs, score_threshold if score_threshold is not None else self.DEFAULT_SCORE_THRESHOLD
            )

            # 8. Calculate usage with actual token count
            usage = self._create_usage(model, credentials, total_tokens)

            result = RerankResult(
                model=model,
                docs=rerank_documents,
                usage=usage
            )

            logger.debug("Rerank completed successfully")
            return result

        except TencentCloudSDKException as e:
            logger.error(f"TencentCloud SDK Error: {str(e)}", exc_info=True)
            raise InvokeError(f"API request failed: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise InvokeError(f"Processing failed: {str(e)}")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate Tencent Cloud credentials

        :param model: Model name
        :param credentials: Authentication credentials
        :raises CredentialsValidateFailedError: If credentials validation fails
        """
        try:
            # 1. Validate required fields
            if not credentials.get("secret_id") or not credentials.get("secret_key"):
                raise CredentialsValidateFailedError("Missing required credentials: secret_id and secret_key")

            # 2. Initialize client
            client = self._setup_es_client(credentials)

            # 3. Test API call
            test_params = {
                "ModelName": model,
                "Query": "credentials validation test",
                "Documents": ["test document"],
                "TopN": 1,
                "ReturnDocuments": True
            }

            req = models.RunRerankRequest()
            req.from_json_string(json.dumps(test_params))

            response = client.RunRerank(req)

            # 4. Check response
            if not response:
                raise CredentialsValidateFailedError("API returned empty response")

            # Check if response has Error field
            if hasattr(response, 'Error') and response.Error:
                error_msg = getattr(response.Error, 'Message', 'Unknown error')
                raise CredentialsValidateFailedError(f"API test failed: {error_msg}")

            logger.info("Credentials validation successful")

        except TencentCloudSDKException as e:
            raise CredentialsValidateFailedError(f"API authentication failed: {e.message}")
        except Exception as e:
            raise CredentialsValidateFailedError(f"Validation error: {str(e)}")

    def _setup_es_client(self, credentials: dict) -> es_client.EsClient:
        """
        Standardized Tencent Cloud client initialization using es_client

        :param credentials: Authentication credentials
        :return: EsClient instance
        :raises CredentialsValidateFailedError: If required credentials are missing
        """
        try:
            secret_id = credentials.get("secret_id")
            secret_key = credentials.get("secret_key")

            if not secret_id or not secret_key:
                raise CredentialsValidateFailedError("Missing required credentials: secret_id and secret_key")

            cred = credential.Credential(secret_id, secret_key)

            http_profile = HttpProfile()
            http_profile.endpoint = self.API_ENDPOINT
            http_profile.reqTimeout = 30  # Set timeout

            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile

            # Get region from credentials or use default
            region = credentials.get("region", self.DEFAULT_API_REGION)

            return es_client.EsClient(cred, region, client_profile)
        except KeyError as e:
            raise CredentialsValidateFailedError(f"Missing credential field: {str(e)}")
        except Exception as e:
            raise CredentialsValidateFailedError(f"Client setup failed: {str(e)}")

    def _validate_input_params(self, query: str, docs: List[str]) -> None:
        """
        Validate input parameters

        :param query: Query text
        :param docs: Documents list
        :raises InvokeError: If parameter validation fails
        """
        if not query or not isinstance(query, str):
            raise InvokeError("Query must be a non-empty string")

        if not isinstance(docs, list):
            raise InvokeError("Documents must be a list")

    def _build_request_params(self, model: str, query: str, docs: List[str], top_n: Optional[int]) -> dict:
        """
        Build request parameters

        :param model: Model name
        :param query: Query text
        :param docs: Documents list
        :param top_n: Return count
        :return: Request parameters dictionary
        """
        return {
            "ModelName": model,
            "Query": query,
            "Documents": docs,
            "TopN": top_n or min(len(docs), self.DEFAULT_TOP_N),
            "ReturnDocuments": True
        }

    def _process_response(self, response: object, original_docs: List[str],
                          score_threshold: float) -> tuple[List[RerankDocument], int]:
        """
        Process API response and extract rerank results and token usage

        :param response: API response
        :param original_docs: Original documents list
        :param score_threshold: Score threshold
        :return: tuple of (reranked documents list, total_tokens)
        :raises InvokeError: If response processing fails
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

        # Extract token usage from response
        total_tokens = 0
        if hasattr(resp_data, 'Usage') and resp_data.Usage:
            usage_data = resp_data.Usage
            if hasattr(usage_data, 'TotalTokens'):
                total_tokens = int(usage_data.TotalTokens)
                logger.debug(f"Extracted total tokens from response: {total_tokens}")
            else:
                logger.warning("Usage data found but TotalTokens field missing, falling back to document count")
                total_tokens = len(original_docs)
        else:
            logger.warning("Usage data not found in response, falling back to document count")
            total_tokens = len(original_docs)

        rerank_documents = []
        valid_count = 0
        filtered_count = 0

        for item in resp_data.Data:
            try:
                score = getattr(item, 'RelevanceScore', None)
                document_text = getattr(item, 'Document', None)
                index = getattr(item, 'Index', None)

                # Skip invalid items
                if score is None or document_text is None:
                    filtered_count += 1
                    continue

                # Filter items below threshold
                if score < score_threshold:
                    filtered_count += 1
                    continue

                rerank_documents.append(
                    RerankDocument(
                        index=index if index is not None else valid_count,
                        score=float(score),
                        text=document_text
                    )
                )
                valid_count += 1

            except Exception as e:
                logger.warning(f"Failed to process rerank item: {str(e)}")
                filtered_count += 1
                continue

        # Sort by score in descending order
        rerank_documents_sorted = sorted(rerank_documents, key=lambda x: x.score, reverse=True)

        logger.info(f"Processed {valid_count} valid documents, filtered {filtered_count} documents, total tokens: {total_tokens}")

        return rerank_documents_sorted, total_tokens

    def _create_usage(self, model: str, credentials: dict, total_tokens: int) -> dict:
        """
        Create usage statistics with actual token count using framework pricing

        :param model: Model name
        :param credentials: Authentication credentials
        :param total_tokens: Actual token count from API response
        :return: Usage dictionary
        """
        latency = time.perf_counter() - self.started_at

        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=total_tokens
        )

        return {
            "tokens": total_tokens,
            "total_tokens": total_tokens,
            "unit_price": input_price_info.unit_price,
            "price_unit": input_price_info.unit,
            "total_price": input_price_info.total_amount,
            "currency": input_price_info.currency,
            "latency": float(latency)
        }

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], List[type[Exception]]]:
        """
        Map model invoke error to unified error

        :return: Invoke error mapping
        """
        return {InvokeError: [TencentCloudSDKException]}