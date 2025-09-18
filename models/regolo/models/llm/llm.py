import json
import logging
from collections.abc import Generator
from decimal import Decimal
from typing import Optional, Union
from urllib.parse import urlparse

import requests

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
)
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
    PriceConfig,
)
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
)

logger = logging.getLogger(__name__)


class RegoloLargeLanguageModel(OAICompatLargeLanguageModel):
    """
    Model class for Regolo large language model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        self._add_custom_parameters(credentials)
        # Workaround: disable streaming for models affected by LiteLLM streaming bug
        # gpt-oss-120b returns non-JSON chunks with 'thinking' key that break parser
        if isinstance(model, str) and (model.lower().startswith("gpt-oss") or model.lower() == "gpt-oss-120b"):
            stream = False
        # Regolo supports standard OpenAI-compatible chat completions
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    # rely on OAICompatLargeLanguageModel for streaming and completion handling

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        """
        Generate custom model entities from credentials
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.LLM,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                "context_size": int(credentials.get("context_size", 4096)),
                "mode": "chat",
            },
            parameter_rules=[],
            pricing=PriceConfig(
                input=Decimal(credentials.get("input_price", 0)),
                unit=Decimal(credentials.get("unit", 0)),
                currency=credentials.get("currency", "EUR"),
            ),
        )
        return entity

    # use parent class defaults for token counting and error mapping

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        # ensure mode
        credentials["mode"] = "chat"
        # map provider key to OpenAI-compatible field
        if "regolo_api_key" in credentials and credentials.get("regolo_api_key"):
            credentials["openai_api_key"] = credentials["regolo_api_key"]
        elif "api_key" in credentials and credentials.get("api_key"):
            credentials["openai_api_key"] = credentials["api_key"]

        # mirror key to alternative fields some base classes/tools may read
        if credentials.get("openai_api_key") and not credentials.get("api_key"):
            credentials["api_key"] = credentials["openai_api_key"]

        # default endpoint base
        if "endpoint_url" not in credentials or not credentials.get("endpoint_url"):
            credentials["endpoint_url"] = "https://api.regolo.ai/v1"
        else:
            # normalize to scheme://host
            parsed = urlparse(credentials["endpoint_url"])
            if parsed.scheme and parsed.netloc:
                credentials["endpoint_url"] = f"{parsed.scheme}://{parsed.netloc}"
            else:
                credentials["endpoint_url"] = "https://api.regolo.ai/v1"

        # mirror endpoint to commonly used aliases
        if credentials.get("endpoint_url"):
            # Some OpenAI-compatible integrations expect these names
            credentials.setdefault("openai_api_base", credentials["endpoint_url"])
            credentials.setdefault("base_url", credentials["endpoint_url"]) 
