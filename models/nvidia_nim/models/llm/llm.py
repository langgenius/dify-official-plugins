import difflib
import logging
from urllib.parse import urlparse

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)

NVIDIA_BUILD_DEFAULT_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_BUILD_HOST = "integrate.api.nvidia.com"
CATALOG_TIMEOUT = (5, 10)


class NVIDIANIMProvider(OAICompatLargeLanguageModel):
    """
    Model class for NVIDIA NIM large language model.
    """

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials with catalog auto-detection.

        - Empty endpoint_url falls back to the NVIDIA Build catalog
          (https://integrate.api.nvidia.com/v1).
        - When the endpoint serves an OpenAI-compatible model list, the model
          name is checked against it (with typo suggestions). Only the NVIDIA
          Build catalog hard-fails on unknown models; custom endpoints (e.g.
          self-hosted NIMs behind a proxy) fall back to the ping below.
        - The inherited ping to /chat/completions remains the authoritative
          check for the API key and model access.
        """
        endpoint_url = (credentials.get("endpoint_url") or "").strip().rstrip("/")
        if not endpoint_url:
            endpoint_url = NVIDIA_BUILD_DEFAULT_URL

        credentials["endpoint_url"] = endpoint_url
        if not credentials.get("mode"):
            credentials["mode"] = "chat"
        if credentials.get("api_key") is not None:
            credentials["api_key"] = credentials["api_key"].strip()

        try:
            is_build_catalog = urlparse(endpoint_url).hostname == NVIDIA_BUILD_HOST
        except ValueError:
            is_build_catalog = False
        if is_build_catalog and not (credentials.get("api_key") or "").strip():
            raise CredentialsValidateFailedError(
                "API Key is required when using the NVIDIA Build cloud catalog"
            )

        self._check_model_in_catalog(model, credentials, hard_fail=is_build_catalog)

        super().validate_credentials(model, credentials)

    def _check_model_in_catalog(
        self,
        model: str,
        credentials: dict,
        *,
        hard_fail: bool = True,
    ) -> None:
        """
        Soft catalog check: verify the model exists in the model list served
        by the endpoint. Failures (non-200, timeouts, invalid payloads) are
        logged and skipped so custom NIM endpoints that only expose
        /chat/completions keep working. Unknown models hard-fail only for the
        NVIDIA Build catalog; custom endpoints delegate to the ping.
        """
        headers = {"Accept": "application/json"}
        if api_key := (credentials.get("api_key") or "").strip():
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.get(
                f"{credentials['endpoint_url']}/models",
                headers=headers,
                timeout=CATALOG_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException as ex:
            logger.warning(
                "NVIDIA NIM: catalog check skipped for %s: %s",
                credentials["endpoint_url"],
                ex,
            )
            return

        if response.status_code != requests.codes.ok:
            logger.warning(
                "NVIDIA NIM: catalog check skipped for %s (status %s)",
                credentials["endpoint_url"],
                response.status_code,
            )
            return

        try:
            payload = response.json()
        except ValueError:
            logger.warning(
                "NVIDIA NIM: catalog check skipped, invalid JSON from %s",
                credentials["endpoint_url"],
            )
            return

        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            logger.warning(
                "NVIDIA NIM: catalog check skipped, no model list from %s",
                credentials["endpoint_url"],
            )
            return

        model_ids = sorted(
            item_id
            for item in items
            if isinstance(item, dict)
            and isinstance((item_id := item.get("id")), str)
            and item_id.strip()
        )
        if not model_ids:
            logger.warning(
                "NVIDIA NIM: catalog check skipped, empty model list from %s",
                credentials["endpoint_url"],
            )
            return

        if model in model_ids:
            return

        suggestions = difflib.get_close_matches(model, model_ids, n=3)
        if hard_fail:
            message = (
                f"Model '{model}' was not found in the model list served by "
                f"{credentials['endpoint_url']}"
            )
            if suggestions:
                message += f". Did you mean: {', '.join(suggestions)}?"
            raise CredentialsValidateFailedError(message)

        logger.warning(
            "NVIDIA NIM: model '%s' not listed by %s%s; continuing (chat ping will decide)",
            model,
            credentials["endpoint_url"],
            f" (did you mean: {', '.join(suggestions)}?)" if suggestions else "",
        )
