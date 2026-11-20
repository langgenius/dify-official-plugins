import json
from collections.abc import Generator

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMMode, LLMResult, LLMResultChunk
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError

SPEND_LOGS_METADATA_HEADER = "x-litellm-spend-logs-metadata"
SPEND_LOGS_USER_ID_KEY = "dify_sys_user_id"
SPEND_LOGS_APP_ID_KEY = "dify_sys_app_id"


def _parse_spend_logs_metadata(raw: object) -> dict:
    """Parse the optional `spend_logs_metadata` credential into a JSON object."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        msg = "spend_logs_metadata must be a JSON object"
        raise ValueError(msg)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"spend_logs_metadata is not valid JSON: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(value, dict):
        msg = "spend_logs_metadata must be a JSON object"
        raise ValueError(msg)
    return value


def _current_app_id() -> str | None:
    """Return the Dify app ID for the running invocation, if the SDK exposes it."""
    try:
        from dify_plugin import get_current_session

        session = get_current_session()
    except Exception:
        # Telemetry must never break generation.
        return None
    app_id = getattr(session, "app_id", None) if session is not None else None
    return app_id if isinstance(app_id, str) and app_id else None


def build_spend_logs_metadata(
    credentials: dict,
    user: str | None,
    app_id: str | None = None,
) -> str | None:
    """Build the header value LiteLLM uses to tag spend logs.

    Dify's end-user and app IDs are always included so proxy-side cost reports
    can be grouped per user and per app, and any extra keys from the credential
    form are merged on top of them.
    """
    metadata: dict = {}
    if user:
        metadata[SPEND_LOGS_USER_ID_KEY] = user
    if app_id:
        metadata[SPEND_LOGS_APP_ID_KEY] = app_id
    metadata.update(_parse_spend_logs_metadata(credentials.get("spend_logs_metadata")))
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))


class LiteLLMLargeLanguageModel(OAICompatLargeLanguageModel):
    """Chat and completion models served by a LiteLLM Proxy.

    When a model answers with tool calls only, the proxy can leave out
    `message.content` or set it to `null`. The shared base class reads
    `message["content"]` and fails with `KeyError`, so this class handles
    non-streaming responses itself and treats a missing value as an empty string.
    """

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """Reject a malformed spend-logs metadata value before the model is saved."""
        try:
            _parse_spend_logs_metadata(credentials.get("spend_logs_metadata"))
        except ValueError as exc:
            raise CredentialsValidateFailedError(str(exc)) from exc
        super().validate_credentials(model, credentials)

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
    ) -> LLMResult | Generator[LLMResultChunk, None, None]:
        """Invoke the model with LiteLLM spend-log metadata attached.

        The base class forwards `extra_headers` to the proxy, so the metadata is
        added there instead of rebuilding the request. The feature is opt-in and
        disabled by default, so existing models behave exactly as before.
        """
        if credentials.get("enable_spend_logs_metadata") != "enabled":
            return super()._invoke(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
            )
        try:
            metadata = build_spend_logs_metadata(credentials, user, _current_app_id())
        except ValueError as exc:
            raise InvokeError(str(exc)) from exc
        if metadata is not None:
            credentials = {
                **credentials,
                "extra_headers": {
                    **(credentials.get("extra_headers") or {}),
                    SPEND_LOGS_METADATA_HEADER: metadata,
                },
            }
        return super()._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        response_json: dict = response.json()

        choices = response_json.get("choices")
        if not choices:
            raise InvokeError("LiteLLM Proxy returned a response without choices")
        output = choices[0]

        completion_type = LLMMode.value_of(credentials["mode"])
        function_calling_type = credentials.get("function_calling_type", "no_call")

        content = ""
        tool_calls = None
        if completion_type is LLMMode.CHAT:
            message = output.get("message") or {}
            content = message.get("content")
            if function_calling_type == "tool_call":
                tool_calls = message.get("tool_calls")
            elif function_calling_type == "function_call":
                tool_calls = message.get("function_call")
        else:
            content = output.get("text")
        if not isinstance(content, str):
            content = ""

        assistant_message = AssistantPromptMessage(content=content, tool_calls=[])
        if tool_calls:
            if function_calling_type == "tool_call":
                assistant_message.tool_calls = self._extract_response_tool_calls(tool_calls)
            else:
                function_call = self._extract_response_function_call(tool_calls)
                assistant_message.tool_calls = [function_call] if function_call else []

        usage = response_json.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
        completion_tokens = usage.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = self._num_tokens_from_string(content)

        return LLMResult(
            id=response_json.get("id"),
            model=response_json.get("model", model),
            message=assistant_message,
            usage=self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens),
        )
