"""Switchyard LLM: route each call between a capable and an efficient upstream with libsy."""

import asyncio
import hashlib
import logging
import threading
from collections.abc import Generator, Iterator, Mapping
from typing import override

import httpx
from dify_plugin import LargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    UserPromptMessage,
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
from switchyard.libsy import Algorithm, LibsyError, RoutingOutcome, Step, algorithms

from .wire import (
    Delta,
    Upstream,
    UpstreamAuthError,
    UpstreamBadRequestError,
    UpstreamError,
    UpstreamRateLimitError,
    UpstreamServerError,
    open_stream,
    to_ir,
)

logger = logging.getLogger(__name__)

TIERS = ("capable", "efficient")
# libsy target IDs are the tier names, so both tiers may use the same upstream model name.
# "any" must list every target: libsy validates selections against it and uses it for fallback.
RUNTIME_MODELS = {"capable": ["capable"], "efficient": ["efficient"], "any": list(TIERS)}

# One algorithm per routing config, shared across requests: the stage router keeps per-session
# state (such as the capable hold after an escalation) inside the algorithm.
_algorithms: dict[tuple[str, float], Algorithm] = {}
_algorithms_lock = threading.Lock()


def _algorithm(credentials: Mapping) -> Algorithm:
    picker = credentials.get("picker") or "efficient_first"
    threshold = float(credentials.get("confidence_threshold") or 0.5)
    with _algorithms_lock:
        key = (picker, threshold)
        if key not in _algorithms:
            _algorithms[key] = algorithms.stage_router(
                picker=picker, confidence_threshold=threshold
            )
        return _algorithms[key]


def _upstreams(credentials: Mapping) -> dict[str, Upstream]:
    return {
        tier: Upstream(
            endpoint_url=credentials[f"{tier}_endpoint_url"].rstrip("/"),
            api_key=credentials.get(f"{tier}_api_key") or "",
            model=credentials[f"{tier}_model"],
            api_format=credentials.get(f"{tier}_api_format") or "responses",
        )
        for tier in TIERS
    }


def _session_id(user: str | None, ir: dict) -> str | None:
    """Dify does not pass a conversation ID to model plugins.

    Approximate one from the end user and the first user message, which stays fixed for the
    whole conversation. Two conversations by one user that open with the same message share
    routing state.
    """
    first = next((m for m in ir["messages"] if m["role"] == "user"), None)
    if not user or first is None:
        return None
    return hashlib.sha256(f"{user}\0{first['content']}".encode()).hexdigest()[:32]


async def _decide(algorithm: Algorithm, ir: dict, headers: dict | None) -> RoutingOutcome:
    async for step in algorithm.run_stream(ir, RUNTIME_MODELS, headers=headers):
        match step:
            case Step.Done(outcome):
                return outcome
            case _:
                # The stage router without an LLM fallback makes no routing-time model calls.
                raise LibsyError("unexpected routing-time model call")
    raise LibsyError("algorithm ended without a routing outcome")


class SwitchyardLargeLanguageModel(LargeLanguageModel):
    @override
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
    ) -> Generator[LLMResultChunk, None, None]:
        ir = to_ir(prompt_messages)
        session = _session_id(user, ir)
        headers = {"x-switchyard-session-id": session} if session else None
        outcome = asyncio.run(_decide(_algorithm(credentials), ir, headers))
        evidence = outcome.metadata.evidence if outcome.metadata else None
        upstreams = _upstreams(credentials)

        # Open the stream here, not in the generator, so failures before the first token can
        # fall back to the next candidate and reach Dify as mapped invoke errors.
        error: Exception | None = None
        for tier in outcome.selected_model_ids:
            upstream = upstreams[tier]
            try:
                deltas = open_stream(upstream, outcome.request, tools, model_parameters, stop)
            except (UpstreamError, httpx.TransportError) as e:
                logger.warning("switchyard: %s (%s) failed, trying next: %s", tier, upstream.model, e)
                error = e
                continue
            logger.info("switchyard: routed to %s (%s), evidence=%s", tier, upstream.model, evidence)
            return self._chunks(model, credentials, upstream.model, deltas)
        assert error is not None
        raise error

    def _chunks(
        self, model: str, credentials: dict, served_by: str, deltas: Iterator[Delta]
    ) -> Generator[LLMResultChunk, None, None]:
        index = 0
        usage = (0, 0)
        in_reasoning = False

        def chunk(message: AssistantPromptMessage, **delta) -> LLMResultChunk:
            nonlocal index
            index += 1
            return LLMResultChunk(
                model=served_by,
                delta=LLMResultChunkDelta(index=index - 1, message=message, **delta),
            )

        for delta in deltas:
            # Dify shows reasoning wrapped in <think> tags.
            content = ""
            if delta.reasoning:
                content += delta.reasoning if in_reasoning else f"<think>\n{delta.reasoning}"
                in_reasoning = True
            if delta.text:
                if in_reasoning:
                    content += "\n</think>\n"
                    in_reasoning = False
                content += delta.text
            if content:
                yield chunk(AssistantPromptMessage(content=content))
            if delta.tool_calls:
                tool_calls = [
                    AssistantPromptMessage.ToolCall(
                        id=call.id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=call.name, arguments=call.arguments
                        ),
                    )
                    for call in delta.tool_calls
                ]
                yield chunk(AssistantPromptMessage(content="", tool_calls=tool_calls))
            if delta.usage:
                usage = delta.usage
            if delta.finish_reason:
                yield chunk(
                    AssistantPromptMessage(content="\n</think>\n" if in_reasoning else ""),
                    usage=self._calc_response_usage(model, credentials, *usage),
                    finish_reason=delta.finish_reason,
                )

    @override
    def validate_credentials(self, model: str, credentials: Mapping) -> None:
        try:
            _algorithm(credentials)
        except Exception as e:
            raise CredentialsValidateFailedError(f"invalid routing settings: {e}") from e
        ir = to_ir([UserPromptMessage(content="ping")])
        for tier, upstream in _upstreams(credentials).items():
            try:
                for _ in open_stream(upstream, ir, None, {"max_tokens": 16}, None):
                    pass
            except Exception as e:
                raise CredentialsValidateFailedError(
                    f"{tier} upstream ({upstream.model}) failed: {e}"
                ) from e

    @override
    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        text = "".join(m.content for m in prompt_messages if isinstance(m.content, str))
        return self._get_num_tokens_by_gpt2(text)

    @override
    def get_customizable_model_schema(self, model: str, credentials: Mapping) -> AIModelEntity:
        max_tokens = int(credentials.get("max_tokens_to_sample") or 8192)
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.LLM,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            features=[
                ModelFeature.TOOL_CALL,
                ModelFeature.MULTI_TOOL_CALL,
                ModelFeature.STREAM_TOOL_CALL,
                ModelFeature.AGENT_THOUGHT,
            ],
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size") or 128000),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name=DefaultParameterName.TEMPERATURE.value,
                    use_template=DefaultParameterName.TEMPERATURE.value,
                    label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                    type=ParameterType.FLOAT,
                    min=0,
                    max=2,
                    precision=2,
                ),
                ParameterRule(
                    name=DefaultParameterName.TOP_P.value,
                    use_template=DefaultParameterName.TOP_P.value,
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                    type=ParameterType.FLOAT,
                    min=0,
                    max=1,
                    precision=2,
                ),
                ParameterRule(
                    name=DefaultParameterName.MAX_TOKENS.value,
                    use_template=DefaultParameterName.MAX_TOKENS.value,
                    label=I18nObject(en_US="Max Tokens", zh_Hans="最大标记"),
                    type=ParameterType.INT,
                    default=min(4096, max_tokens),
                    min=1,
                    max=max_tokens,
                ),
            ],
        )

    @property
    @override
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [httpx.TransportError],
            InvokeServerUnavailableError: [UpstreamServerError],
            InvokeRateLimitError: [UpstreamRateLimitError],
            InvokeAuthorizationError: [UpstreamAuthError],
            InvokeBadRequestError: [UpstreamBadRequestError, LibsyError, ValueError],
        }
