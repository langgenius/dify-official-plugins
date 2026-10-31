import codecs
import json
import math
import uuid
from collections.abc import Generator

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError
from dify_plugin.interfaces.model.openai_compatible.llm import _iter_stream_json

from models._credentials import ENDPOINT_URL, validate_model_access


def _has_complete_arguments(arguments: str) -> bool:
    try:
        json.loads(arguments)
    except ValueError:
        return False
    return True


class _ToolCallStreamResponse(requests.Response):
    def __init__(self, response: requests.Response, delimiter: str) -> None:
        super().__init__()
        self.response = response
        self.delimiter = delimiter
        self.encoding = "utf-8"
        self.tool_calls: list[AssistantPromptMessage.ToolCall] = []
        self.indexed_calls: dict[int, AssistantPromptMessage.ToolCall] = {}

    def close(self):
        self.response.close()

    def iter_content(self, chunk_size=512, decode_unicode=False):
        for line in self._iter_events():
            event = line + "\n\n"
            yield event if decode_unicode else event.encode()

    def _iter_events(self):
        for payload in _iter_stream_json(self.response, self.delimiter):
            if not payload.get("choices"):
                yield json.dumps(payload)
                continue
            delta = payload["choices"][0].get("delta", {})
            fragments = delta.get("tool_calls")
            if not fragments:
                yield json.dumps(payload)
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
            yield json.dumps(payload)

        calls = []
        for call in self.tool_calls:
            if not (call.function.name or call.function.arguments):
                continue
            if not call.id:
                call.id = f"chatcmpl-tool-{uuid.uuid4().hex}"
            calls.append({"index": len(calls), **call.model_dump()})
        if calls:
            yield json.dumps({"choices": [{"delta": {"tool_calls": calls}}]})
        yield "data: [DONE]"


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
        return super()._invoke(
            model=model,
            credentials=self._model_credentials(model, credentials),
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeBadRequestError):
            return error
        return super()._transform_invoke_error(error)

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> Generator:
        if credentials.get("function_calling_type") != "tool_call":
            yield from super()._handle_generate_stream_response(
                model, credentials, response, prompt_messages, tools=tools
            )
            return
        delimiter = codecs.decode(
            credentials.get("stream_mode_delimiter", "\n\n"), "unicode_escape"
        )
        adapted = _ToolCallStreamResponse(response, delimiter)
        yield from super()._handle_generate_stream_response(
            model,
            {**credentials, "stream_mode_delimiter": "\n\n"},
            adapted,
            prompt_messages,
            tools=tools,
        )

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
        filtered = super()._validate_and_filter_model_parameters(
            model, model_parameters, credentials
        )
        if model_parameters.get("tool_choice") is not None:
            filtered["tool_choice"] = model_parameters["tool_choice"]
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
        if not (
            tools
            and model_parameters.get("tool_choice") is not None
            and credentials.get("function_calling_type") == "tool_call"
        ):
            model_parameters = {
                key: value for key, value in model_parameters.items() if key != "tool_choice"
            }
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
