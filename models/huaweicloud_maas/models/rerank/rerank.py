from typing import Optional
from dify_plugin.interfaces.model.openai_compatible.rerank import OAICompatRerankModel
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.entities.model.rerank import RerankResult


class HuaweiCloudMaasRerankModel(OAICompatRerankModel):
    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

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
        self._add_custom_parameters(credentials)
        return super()._invoke(
            model, credentials, query, docs, score_threshold, top_n, user
        )

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        credentials["endpoint_url"] = str(
            credentials.get("endpoint_url", "https://api.modelarts-maas.com/v1")
        )
