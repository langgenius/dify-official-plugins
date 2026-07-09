from __future__ import annotations

from collections.abc import Generator
from typing import Any

from openai import OpenAI

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import AIModelEntity, FetchFrom
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin.errors.model import CredentialsValidateFailedError

from ..common_openai import _CommonOpenAI
from . import chat, responses, stream as response_stream, tokens

CHAT_ONLY_PREFIXES = ("gpt-audio",)
RESPONSES_ONLY_PREFIXES = (
    "gpt-5.2-pro",
    "gpt-5.4-pro",
    "gpt-5.5-pro",
    "o3-pro",
)
NON_STREAMING_MODELS = {
    "gpt-5.5-pro",
    "gpt-5.5-pro-2026-04-23",
    "gpt-audio-mini",
    "gpt-audio-mini-2025-12-15",
    "o3-pro",
}


class OpenAILargeLanguageModel(_CommonOpenAI, LargeLanguageModel):
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
        params = model_parameters.copy()
        if params.pop("enable_stream", None) is False or model in NON_STREAMING_MODELS:
            stream = False
        if params.get("service_tier") in (None, ""):
            params.pop("service_tier", None)

        return self._chat_generate(
            model,
            credentials,
            prompt_messages,
            params,
            tools,
            stop,
            stream,
            user,
        )

    def _chat_generate(
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
        client = OpenAI(**self._to_credential_kwargs(credentials))
        if _uses_responses(model, credentials):
            if stream:
                return self._stream_with_error_mapping(
                    response_stream.generate(
                        self,
                        client,
                        model,
                        credentials,
                        prompt_messages,
                        model_parameters,
                        tools,
                        stop,
                        user,
                    )
                )
            return responses.generate(
                self,
                client,
                model,
                credentials,
                prompt_messages,
                model_parameters,
                tools,
                stop,
                user,
            )
        result = chat.generate_chat(
            self,
            client,
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )
        if stream:
            return self._stream_with_error_mapping(result)
        return result

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            client = OpenAI(**self._to_credential_kwargs(credentials))
            if model.startswith("ft:") and model not in {
                item.model for item in self.remote_models(credentials)
            }:
                raise CredentialsValidateFailedError(
                    f"Fine-tuned model {model} not found"
                )

            if _uses_responses(model, credentials):
                client.responses.create(
                    model=model,
                    input="ping",
                    max_output_tokens=20,
                    store=False,
                )
            else:
                limit = (
                    {"max_completion_tokens": 20}
                    if chat.uses_max_completion_tokens(model)
                    else {"max_tokens": 20}
                )
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    **limit,
                )
        except CredentialsValidateFailedError:
            raise
        except Exception as error:
            raise CredentialsValidateFailedError(str(error)) from error

    def remote_models(self, credentials: dict) -> list[AIModelEntity]:
        schemas = {item.model: item for item in self.predefined_models()}
        client = OpenAI(**self._to_credential_kwargs(credentials))
        result = []
        for remote in client.models.list():
            if not remote.id.startswith("ft:"):
                continue
            schema = schemas.get(_base_model(remote.id))
            if schema is None:
                continue
            result.append(
                schema.model_copy(
                    deep=True,
                    update={
                        "model": remote.id,
                        "label": I18nObject(zh_hans=remote.id, en_us=remote.id),
                        "fetch_from": FetchFrom.CUSTOMIZABLE_MODEL,
                    },
                )
            )
        return result

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        schema = {item.model: item for item in self.predefined_models()}.get(
            _base_model(model)
        )
        if schema is None:
            raise ValueError(f"Base model {_base_model(model)} not found")
        return schema.model_copy(
            deep=True,
            update={
                "model": model,
                "label": I18nObject(zh_hans=model, en_us=model),
                "fetch_from": FetchFrom.CUSTOMIZABLE_MODEL,
            },
        )

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return tokens.count_messages(_base_model(model), prompt_messages, tools)

    def _num_tokens_from_string(
        self,
        model: str,
        text: str,
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return tokens.count_text(model, text) + (
            tokens.count_messages(model, [], tools) - 3 if tools else 0
        )

    def _num_tokens_from_messages(
        self,
        model: str,
        messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return tokens.count_messages(model, messages, tools)


def _uses_responses(model: str, credentials: dict[str, Any]) -> bool:
    if model.startswith(CHAT_ONLY_PREFIXES):
        return False
    if model.startswith(RESPONSES_ONLY_PREFIXES):
        return True
    return credentials.get("api_protocol") != "chat"


def _base_model(model: str) -> str:
    return model.split(":", 2)[1] if model.startswith("ft:") else model
