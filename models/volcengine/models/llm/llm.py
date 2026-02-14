import logging
from collections.abc import Generator
from typing import Optional

from volcenginesdkarkruntime import Ark  # type: ignore

from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)


def _to_openai_messages(messages: list[PromptMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if isinstance(m, SystemPromptMessage):
            out.append({"role": "system", "content": m.content})
        elif isinstance(m, UserPromptMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AssistantPromptMessage):
            out.append({"role": "assistant", "content": m.content})
        elif isinstance(m, ToolPromptMessage):
            # Ark is OpenAI-compatible; tool messages are supported in chat.completions
            out.append({"role": "tool", "content": m.content, "tool_call_id": m.tool_call_id})
        else:
            out.append({"role": "user", "content": str(getattr(m, "content", m))})
    return out


class VolcengineArkLargeLanguageModel(LargeLanguageModel):
    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            client = Ark(base_url=credentials["api_endpoint_host"], api_key=credentials["ark_api_key"])
            # minimal non-stream call
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=8,
            )
        except Exception as e:
            raise CredentialsValidateFailedError(e)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        # No official token counter exposed here; fall back to rough estimate.
        # This is acceptable for plugin implementations that do not support token counting.
        text = "".join(getattr(m, "content", "") if isinstance(getattr(m, "content", ""), str) else "" for m in prompt_messages)
        return max(1, len(text) // 4)

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
        client = Ark(base_url=credentials["api_endpoint_host"], api_key=credentials["ark_api_key"])

        params = {
            "model": model,
            "messages": _to_openai_messages(prompt_messages),
            "temperature": model_parameters.get("temperature"),
            "top_p": model_parameters.get("top_p"),
            "max_tokens": model_parameters.get("max_tokens"),
            "stop": stop,
        }

        def _handle_stream() -> Generator:
            try:
                resp = client.chat.completions.create(**{k: v for k, v in params.items() if v is not None}, stream=True)
                for idx, chunk in enumerate(resp):
                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue
                    delta = getattr(choice, "delta", None)
                    content = getattr(delta, "content", None) if delta else None
                    if content is None:
                        content = ""
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=idx,
                            message=AssistantPromptMessage(content=content or "", tool_calls=[]),
                            usage=None,
                            finish_reason=getattr(choice, "finish_reason", None),
                        ),
                    )
            except Exception as e:
                raise InvokeError(str(e))

        def _handle_block() -> LLMResult:
            try:
                resp = client.chat.completions.create(**{k: v for k, v in params.items() if v is not None}, stream=False)
                choice = resp.choices[0]
                msg = choice.message
                content = getattr(msg, "content", "") or ""
                return LLMResult(
                    model=model,
                    prompt_messages=prompt_messages,
                    message=AssistantPromptMessage(content=content, tool_calls=[]),
                    usage=None,
                )
            except Exception as e:
                raise InvokeError(str(e))

        return _handle_stream() if stream else _handle_block()

    def get_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        rules: list[ParameterRule] = [
            ParameterRule(
                name="temperature",
                type=ParameterType.FLOAT,
                default=0.7,
                min=0.0,
                max=2.0,
                label=I18nObject(en_US="Temperature", zh_Hans="温度"),
            ),
            ParameterRule(
                name="top_p",
                type=ParameterType.FLOAT,
                default=1.0,
                min=0.0,
                max=1.0,
                label=I18nObject(en_US="Top P", zh_Hans="Top P"),
            ),
            ParameterRule(
                name="max_tokens",
                type=ParameterType.INT,
                default=512,
                min=1,
                max=32768,
                label=I18nObject(en_US="Max Tokens", zh_Hans="最大生成长度"),
            ),
        ]

        model_properties = {
            ModelPropertyKey.MODE: "chat",
        }

        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            fetch_from=FetchFrom.PREDEFINED_MODEL,
            model_type=ModelType.LLM,
            model_properties=model_properties,
            parameter_rules=rules,
            features=[ModelFeature.AGENT_THOUGHT],
        )
