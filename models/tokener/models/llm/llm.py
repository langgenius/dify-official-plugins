import json
import math
import uuid
from collections.abc import Generator
from copy import deepcopy

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageFunction,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError

from models._credentials import ENDPOINT_URL, validate_model_access
from models.llm._legacy_parameters import (
    TRANSPORT_FIELDS,
    legacy_parameter_names,
    prepare_legacy_parameters,
)
from models.llm._sse import ChatCompletionSSEStreamResponse

# A model's public name does not prove that its deployment uses native Gemini.
# Enable only after verifying the server's reviewed LiteLLM transport contract.
GEMINI_NATIVE_TRANSPORT_CONFIRMED = False
GEMINI_GOOGLE_OPENAI_TRANSPORT_CONFIRMED = False


class _CompatibilityParameters(dict):
    """Request-local state, never a JSON key or shared model-instance attribute."""

    def __init__(self, filtered: dict, compatibility_inputs: dict):
        super().__init__(filtered)
        self.compatibility_inputs = deepcopy(compatibility_inputs)


def _has_complete_arguments(arguments: str) -> bool:
    try:
        json.loads(arguments)
    except ValueError:
        return False
    return True


class _ToolCallStreamResponse(requests.Response):
    def __init__(self, response: requests.Response) -> None:
        super().__init__()
        self.response = response
        self.tool_calls: list[AssistantPromptMessage.ToolCall] = []
        self.indexed_calls: dict[int, AssistantPromptMessage.ToolCall] = {}

    def iter_lines(self, chunk_size=512, decode_unicode=False, delimiter=None):
        for line in self.response.iter_lines(
            chunk_size=chunk_size, decode_unicode=decode_unicode, delimiter=delimiter
        ):
            decoded = line.strip().removeprefix("data:").lstrip()
            try:
                payload = json.loads(decoded)
            except (ValueError, TypeError):
                yield line
                continue
            if not isinstance(payload, dict) or not payload.get("choices"):
                yield line
                continue
            delta = payload["choices"][0].get("delta", {})
            fragments = delta.get("tool_calls")
            if not fragments:
                yield line
                continue
            for fragment in fragments:
                index = fragment.get("index")
                call_id = fragment.get("id")
                function = fragment.get("function") or {}
                name = function.get("name") or ""
                indexed = self.indexed_calls.get(index) if isinstance(index, int) else None
                last = self.tool_calls[-1] if self.tool_calls else None
                current = None
                if call_id:
                    current = next((call for call in self.tool_calls if call.id == call_id), None)
                    if current is None:
                        candidate = indexed if isinstance(index, int) else last
                        if (
                            candidate is not None
                            and not candidate.id
                            and not (name and candidate.function.name)
                            and not _has_complete_arguments(candidate.function.arguments)
                        ):
                            current = candidate
                elif name:
                    candidate = indexed if isinstance(index, int) else last
                    if (
                        candidate is not None
                        and not candidate.function.name
                        and not (
                            function.get("arguments")
                            and _has_complete_arguments(candidate.function.arguments)
                        )
                    ):
                        current = candidate
                else:
                    current = indexed or last
                    if (
                        isinstance(index, int)
                        and indexed is None
                        and (
                            not function
                            or (
                                last is not None
                                and _has_complete_arguments(last.function.arguments)
                                and not (function.get("arguments") or "").isspace()
                            )
                            or (last is not None and not last.function.name and not last.id)
                        )
                    ):
                        current = None
                if current is None:
                    current = AssistantPromptMessage.ToolCall(
                        id="",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="", arguments=""
                        ),
                    )
                    self.tool_calls.append(current)
                if isinstance(index, int):
                    self.indexed_calls[index] = current
                if call_id:
                    current.id = call_id
                if fragment.get("type") and function:
                    current.type = fragment["type"]
                if name:
                    current.function.name = name
                current.function.arguments += function.get("arguments") or ""
            delta["tool_calls"] = [{}]
            yield f"data: {json.dumps(payload)}"


class TokenerLargeLanguageModel(OAICompatLargeLanguageModel):
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
        if model == "qwen-long" and any(
            content.type == PromptMessageContentType.DOCUMENT
            for message in prompt_messages
            if isinstance(message.content, list)
            for content in message.content
        ):
            raise InvokeBadRequestError(
                "Tokener.ai cannot process document attachments with qwen-long. "
                "Extract the document text and paste it into the message "
                "instead of attaching the document. "
                "In Workflow or Chatflow, connect a Doc Extractor node's text output "
                "to the LLM node."
            )
        rules = self.get_parameter_rules(model, credentials)
        declared = {rule.name for rule in rules} | {
            rule.use_template for rule in rules if rule.use_template
        }
        if isinstance(model_parameters, _CompatibilityParameters):
            # SDK wrappers may legitimately remove/adjust already-filtered native
            # values. Keep those changes; restore only the compatibility inputs
            # that would otherwise have been lost to the SDK's schema allowlist.
            parameters = {**model_parameters, **deepcopy(model_parameters.compatibility_inputs)}
            adapt = True
        else:
            parameters = deepcopy(model_parameters)
            adapt = bool(legacy_parameter_names(model) & parameters.keys())
        forbidden = TRANSPORT_FIELDS & parameters.keys()
        if forbidden:
            raise InvokeBadRequestError("Transport fields are not model parameters")
        if adapt:
            plan = prepare_legacy_parameters(
                model,
                parameters,
                declared_parameters=declared,
                gemini_native_contract=GEMINI_NATIVE_TRANSPORT_CONFIRMED,
                gemini_google_openai_contract=GEMINI_GOOGLE_OPENAI_TRANSPORT_CONFIRMED,
                has_custom_tools=bool(tools),
            )
            # Call the base SDK filter, not our pre-validation hook a second time.
            filtered = super()._validate_and_filter_model_parameters(
                model, plan.sdk_parameters, credentials
            )
            if plan.sdk_parameters.get("tool_choice") is not None:
                filtered["tool_choice"] = plan.sdk_parameters["tool_choice"]
            parameters = {**filtered, **plan.wire_overrides}
            stream = plan.effective_stream(stream)
        return super()._invoke(
            model=model,
            credentials=self._model_credentials(model, credentials),
            prompt_messages=prompt_messages,
            model_parameters=parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        response = ChatCompletionSSEStreamResponse(response)
        if credentials.get("function_calling_type") != "tool_call":
            yield from super()._handle_generate_stream_response(
                model, credentials, response, prompt_messages
            )
            return
        adapted = _ToolCallStreamResponse(response)
        for chunk in super()._handle_generate_stream_response(
            model, credentials, adapted, prompt_messages
        ):
            if adapted.tool_calls and chunk.delta.usage is not None:
                calls = [
                    call
                    for call in adapted.tool_calls
                    if call.function.name or call.function.arguments
                ]
                for call in calls:
                    if not call.id:
                        call.id = f"chatcmpl-tool-{uuid.uuid4().hex}"
                if calls:
                    yield LLMResultChunk(
                        model=model,
                        delta=LLMResultChunkDelta(
                            index=chunk.delta.index,
                            message=AssistantPromptMessage(content="", tool_calls=calls),
                        ),
                    )
                adapted.tool_calls.clear()
                adapted.indexed_calls.clear()
            yield chunk

    def _validate_and_filter_model_parameters(
        self, model: str, model_parameters: dict, credentials: dict
    ) -> dict:
        rules = self.get_parameter_rules(model, credentials)
        declared = {rule.name for rule in rules} | {
            rule.use_template for rule in rules if rule.use_template
        }
        for name, value in model_parameters.items():
            if name in declared and name in {
                "temperature",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "seed",
            }:
                if isinstance(value, bool) or (
                    isinstance(value, float) and not math.isfinite(value)
                ):
                    raise ValueError(f"Invalid numeric parameter: {name}")
        forbidden = TRANSPORT_FIELDS & model_parameters.keys()
        if forbidden:
            raise InvokeBadRequestError("Transport fields are not model parameters")
        compatibility_inputs = None
        parameters = deepcopy(model_parameters)
        if legacy_parameter_names(model) & parameters.keys():
            # This hook has no tools argument. Validate values now, but defer
            # deployment gating/tool precedence until _invoke has the actual tools.
            # Treating custom tools as present prevents premature native-tool
            # rejection for a combination the source plugin disables itself.
            preliminary = prepare_legacy_parameters(
                model,
                parameters,
                declared_parameters=declared,
                gemini_native_contract=True,
                has_custom_tools=True,
                defer_schema_tool_conflict=True,
            )
            compatibility_inputs = {
                name: parameters[name] for name in preliminary.consumed_parameters
            }
            parameters = preliminary.sdk_parameters
        filtered = super()._validate_and_filter_model_parameters(model, parameters, credentials)
        if parameters.get("tool_choice") is not None:
            filtered["tool_choice"] = parameters["tool_choice"]
        if compatibility_inputs is not None:
            return _CompatibilityParameters(filtered, compatibility_inputs)
        return filtered

    def _generate(
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
        if (
            tools
            and model_parameters.get("tool_choice") is not None
            and credentials.get("function_calling_type") == "tool_call"
        ):
            model_parameters = {
                **model_parameters,
                "tools": [PromptMessageFunction(function=tool).model_dump() for tool in tools],
            }
            tools = None
        else:
            model_parameters = {
                key: value for key, value in model_parameters.items() if key != "tool_choice"
            }
        if stream:
            # Ask for authoritative usage; do not synthesize a usage frame if the
            # server does not send it. SDK's existing fallback remains unchanged.
            model_parameters["stream_options"] = {"include_usage": True}
        return super()._generate(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        validate_model_access(credentials, model)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return super().get_num_tokens(
            model,
            self._model_credentials(model, credentials),
            prompt_messages,
            tools,
        )

    def _model_credentials(self, model: str, credentials: dict) -> dict:
        resolved = {**credentials, "endpoint_url": ENDPOINT_URL, "mode": "chat"}
        schema = self.get_model_schema(model)
        if schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL} & set(
            schema.features or []
        ):
            resolved["function_calling_type"] = "tool_call"
        return resolved
