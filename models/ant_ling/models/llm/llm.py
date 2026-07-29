import logging
import random
import ssl
import time
from collections.abc import Generator

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from yarl import URL

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT_URL = "https://api.ant-ling.com/v1"
DEFAULT_CONTEXT_SIZE = 256_000
DEFAULT_MAX_TOKENS = 32_768
FUNCTION_CALLING_TYPE = "tool_call"
STREAM_FUNCTION_CALLING = "supported"

REASONING_EFFORT_VALID_VALUES = {"high", "xhigh"}
THINKING_DISABLED = "disabled"

RETRY_BASE_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0)
RETRY_JITTER_RATIO = 0.2
RETRY_MIN_SLEEP = 0.1
MAX_RETRIES = len(RETRY_BASE_DELAYS)

TRANSIENT_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
TRANSIENT_EXCEPTION_TYPES = (
    TimeoutError,
    ConnectionError,
    ssl.SSLError,
    OSError,
)


def _is_transient_error(e: Exception) -> bool:
    if isinstance(e, TRANSIENT_EXCEPTION_TYPES):
        return True

    status_code = getattr(e, "status_code", None) or getattr(e, "code", None)
    if status_code is None and hasattr(e, "response"):
        status_code = getattr(e.response, "status_code", None)

    if isinstance(status_code, int) and status_code in TRANSIENT_HTTP_STATUS_CODES:
        return True

    err_str = str(e).lower()
    err_type_name = type(e).__name__.lower()

    if any(kw in err_str or kw in err_type_name for kw in ("ssl", "timeout", "connection", "rate_limit", "rate limit")):
        return True

    for code_str in ("429", "500", "502", "503", "504"):
        patterns = (
            f"http {code_str}",
            f"status {code_str}",
            f"status_code {code_str}",
            f"code {code_str}",
            f"code: {code_str}",
            f'code": {code_str}',
            f'code":{code_str}',
            f"code': {code_str}",
            f"code':{code_str}",
            f'"{code_str}"',
            f"'{code_str}'",
            f"{code_str} internal",
            f" {code_str} ",
        )
        if any(p in err_str for p in patterns):
            return True

    return False


def _calculate_backoff_sleep(base_delay: float) -> float:
    jitter = random.uniform(-RETRY_JITTER_RATIO * base_delay, RETRY_JITTER_RATIO * base_delay)
    return max(RETRY_MIN_SLEEP, base_delay + jitter)


class AntLingLargeLanguageModel(OAICompatLargeLanguageModel):
    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        self._add_custom_parameters(credentials)

        enable_search = model_parameters.pop("enable_search", None)
        forced_search = model_parameters.pop("forced_search", None)
        reasoning_effort = model_parameters.pop("reasoning_effort", None)
        thinking = model_parameters.pop("thinking", None)

        if enable_search is True:
            model_parameters["enable_search"] = True
            if forced_search is True:
                model_parameters["search_options"] = {"forced_search": True}

        if reasoning_effort in REASONING_EFFORT_VALID_VALUES:
            model_parameters["reasoning"] = {"effort": reasoning_effort}

        if thinking == THINKING_DISABLED:
            model_parameters["thinking"] = {"type": THINKING_DISABLED}

        def _invoke_stream_wrapper():
            for attempt in range(MAX_RETRIES + 1):
                has_yielded = False
                try:
                    res = super(AntLingLargeLanguageModel, self)._invoke(
                        model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
                    )
                    if not isinstance(res, Generator):
                        return res
                    for chunk in res:
                        has_yielded = True
                        yield chunk
                    return
                except Exception as e:
                    if _is_transient_error(e) and attempt < MAX_RETRIES and not has_yielded:
                        sleep_time = _calculate_backoff_sleep(RETRY_BASE_DELAYS[attempt])
                        logger.warning(
                            f"[AntLing] Transient stream error (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                            f"Retrying after {sleep_time:.2f}s..."
                        )
                        time.sleep(sleep_time)
                    else:
                        raise e

        wrapped_res = _invoke_stream_wrapper()
        if not stream:
            try:
                return next(wrapped_res)
            except StopIteration as st:
                return st.value
        return wrapped_res

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        for attempt in range(MAX_RETRIES + 1):
            try:
                super().validate_credentials(model, credentials)
                return
            except Exception as e:
                if _is_transient_error(e) and attempt < MAX_RETRIES:
                    sleep_time = _calculate_backoff_sleep(RETRY_BASE_DELAYS[attempt])
                    logger.warning(
                        f"[AntLing] Transient error during validate_credentials (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                        f"Retrying in {sleep_time:.2f}s..."
                    )
                    time.sleep(sleep_time)
                else:
                    raise e

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity | None:
        self._add_custom_parameters(credentials)
        entity = super().get_customizable_model_schema(model, credentials)
        if not entity:
            return None
        entity.label = I18nObject(en_us=model, zh_hans=model)
        entity.features = [
            ModelFeature.AGENT_THOUGHT,
            ModelFeature.TOOL_CALL,
            ModelFeature.STREAM_TOOL_CALL,
        ]
        entity.model_properties[ModelPropertyKey.CONTEXT_SIZE] = int(
            credentials.get("context_size", DEFAULT_CONTEXT_SIZE)
        )
        entity.model_properties[ModelPropertyKey.MODE] = LLMMode.CHAT.value
        return entity

    @staticmethod
    def _add_custom_parameters(credentials: dict) -> None:
        endpoint_url = (credentials.get("endpoint_url") or "").strip() or DEFAULT_ENDPOINT_URL
        credentials["endpoint_url"] = str(URL(endpoint_url))
        credentials["mode"] = LLMMode.CHAT.value
        credentials["function_calling_type"] = FUNCTION_CALLING_TYPE
        credentials["stream_function_calling"] = STREAM_FUNCTION_CALLING
