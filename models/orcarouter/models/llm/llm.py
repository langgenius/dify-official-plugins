import codecs
import json
from collections.abc import Generator
from typing import Optional, Union, Any

import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMMode,
)
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    UserPromptMessage,
    TextPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageContentType,
    AssistantPromptMessage,
)
from dify_plugin.interfaces.model.openai_compatible.llm import _increase_tool_call
from pydantic import TypeAdapter, ValidationError

from models._endpoint_utils import normalize_endpoint_url


class OrcaRouterLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = normalize_endpoint_url(credentials)
        credentials["mode"] = self.get_model_mode(model).value
        schema = self.get_model_schema(model, credentials)
        if schema and {
            ModelFeature.TOOL_CALL,
            ModelFeature.MULTI_TOOL_CALL,
        }.intersection(schema.features or []):
            credentials["function_calling_type"] = "tool_call"

    def _convert_files_to_text(
        self, messages: list[PromptMessage]
    ) -> list[PromptMessage]:
        """Convert any file content in messages to text descriptions for non-vision models."""
        converted_messages = []
        for message in messages:
            if isinstance(message, UserPromptMessage) and isinstance(
                message.content, list
            ):
                text_parts = []
                for content in message.content:
                    if isinstance(content, TextPromptMessageContent):
                        text_parts.append(content.data)
                    elif isinstance(content, ImagePromptMessageContent):
                        if hasattr(content, "url") and content.url:
                            text_parts.append(f"[Image file uploaded]: {content.url}")
                        else:
                            text_parts.append("[Image file uploaded]")
                    elif (
                        hasattr(content, "type")
                        and content.type == PromptMessageContentType.DOCUMENT
                    ):
                        if hasattr(content, "url") and content.url:
                            text_parts.append(
                                f"[Document file uploaded]: {content.url}"
                            )
                        else:
                            text_parts.append("[Document file uploaded]")
                    else:
                        if hasattr(content, "url"):
                            text_parts.append(f"[File uploaded]: {content.url}")
                        else:
                            text_parts.append(str(content))
                converted_messages.append(UserPromptMessage(content=" ".join(text_parts)))
            else:
                converted_messages.append(message)
        return converted_messages

    @staticmethod
    def _set_orca_extra_body(model_parameters: dict):
        """Wrap OrcaRouter fallback routing params into the request's `extra_body` key.

        OrcaRouter server expects `extra_body: {"models": [...], "route": "fallback"}`
        in the request JSON body. The server parses it then strips it before
        forwarding upstream, so strict providers (OpenAI etc.) don't see the
        non-standard field. Reference: OrcaRouter-O2 middleware/distributor.go
        """
        fallback_models_str = model_parameters.pop("orcarouter_fallback_models", None)
        route = model_parameters.pop("orcarouter_route", None)

        extra_body = model_parameters.get("extra_body") or {}
        if not isinstance(extra_body, dict):
            extra_body = {}

        if isinstance(fallback_models_str, str) and fallback_models_str.strip():
            try:
                parsed = json.loads(fallback_models_str)
                if isinstance(parsed, list):
                    extra_body["models"] = [str(m) for m in parsed if m]
            except (json.JSONDecodeError, TypeError):
                pass

        if isinstance(route, str) and route in {"fallback"}:
            extra_body["route"] = route

        if extra_body:
            model_parameters["extra_body"] = extra_body

    @staticmethod
    def _set_reasoning_params(model: str, model_parameters: dict):
        """Translate Dify-facing reasoning params to upstream-native fields.

        OrcaRouter forwards requests to upstream providers, so we emit each
        provider's native reasoning protocol:

          OpenAI o-series / gpt-5: flat `reasoning_effort`
          Anthropic claude with thinking: nested `thinking: {type, budget_tokens}`
          DeepSeek r1 / reasoner: no controls (auto)
          Others (Gemini, Grok, Qwen, Kimi): flat `reasoning_effort` (best-effort)

        `include_reasoning` (the inverse of exclude_reasoning_tokens) controls
        whether the upstream returns reasoning content in the response stream.
        """
        reasoning_budget = model_parameters.pop("reasoning_budget", None)
        enable_thinking = model_parameters.pop("enable_thinking", None)
        reasoning_effort = model_parameters.pop("reasoning_effort", None)
        exclude_reasoning_tokens = model_parameters.pop(
            "exclude_reasoning_tokens", None
        )

        is_anthropic = model.lower().startswith("anthropic/")

        # OpenAI / Gemini / Grok / Qwen / Kimi: flat reasoning_effort
        if not is_anthropic and isinstance(reasoning_effort, str) and reasoning_effort in (
            "high",
            "medium",
            "low",
            "minimal",
        ):
            model_parameters["reasoning_effort"] = reasoning_effort

        # Anthropic: nested thinking block (native API)
        if is_anthropic:
            thinking_enabled = (
                enable_thinking is True
                or (isinstance(enable_thinking, str) and enable_thinking)
            )
            if thinking_enabled:
                thinking_block: dict[str, Any] = {"type": "enabled"}
                if isinstance(reasoning_budget, int) and reasoning_budget >= 1024:
                    thinking_block["budget_tokens"] = reasoning_budget
                model_parameters["thinking"] = thinking_block

        # include_reasoning: hint to upstream/router to surface reasoning content
        if isinstance(exclude_reasoning_tokens, bool):
            model_parameters["include_reasoning"] = not exclude_reasoning_tokens

    @staticmethod
    def _set_verbosity_params(model_parameters: dict):
        """Pass through `verbosity` for OpenAI-style models that support it."""
        verbosity = model_parameters.pop("verbosity", None)
        if isinstance(verbosity, str) and verbosity in ["low", "medium", "high"]:
            model_parameters["verbosity"] = verbosity

    @staticmethod
    def _set_json_schema_params(model_parameters: dict):
        response_format = model_parameters.get("response_format")
        if response_format and response_format == "json_schema":
            json_schema_str = model_parameters.get("json_schema")
            if json_schema_str:
                json_schema = json.loads(json_schema_str)
                schema = (
                    json_schema.get("schema")
                    if "schema" in json_schema
                    else json_schema
                )
                model_parameters["json_schema"] = json.dumps(
                    {"name": "output", "schema": schema}
                )

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
        self._update_credential(model, credentials)

        model_schema = self.get_model_schema(model, credentials)
        if not (model_schema and ModelFeature.VISION in (model_schema.features or [])):
            prompt_messages = self._convert_files_to_text(prompt_messages)

        self._set_reasoning_params(model, model_parameters)
        self._set_verbosity_params(model_parameters)
        self._set_json_schema_params(model_parameters)
        self._set_orca_extra_body(model_parameters)

        return self._generate(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(model, credentials)
        return super().validate_credentials(model, credentials)

    def _generate(
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
        self._update_credential(model, credentials)
        return super()._generate(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def _wrap_thinking_by_reasoning_content(
        self, delta: dict, is_reasoning: bool
    ) -> tuple[str, bool]:
        """Wrap reasoning chunks in <think> tags so Dify UI renders them as thinking.

        OrcaRouter forwards upstream's native reasoning field, which varies by provider:
          OpenAI o-series: `delta.reasoning_content`
          DeepSeek r1: `delta.reasoning_content`
          Anthropic thinking: `delta.thinking`
        We probe all known field names.
        """
        content = delta.get("content") or ""
        reasoning_content = (
            delta.get("reasoning_content")
            or delta.get("reasoning")
            or delta.get("thinking")
        )

        if reasoning_content:
            if not is_reasoning:
                content = "<think>\n" + reasoning_content
                is_reasoning = True
            else:
                content = reasoning_content
        elif is_reasoning and content:
            content = "\n</think>" + content
            is_reasoning = False
        return content, is_reasoning

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        return super().get_customizable_model_schema(model, credentials)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        self._update_credential(model, credentials)
        return super().get_num_tokens(model, credentials, prompt_messages, tools)

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        chunk_index = 0
        full_assistant_content = ""
        tools_calls: list[AssistantPromptMessage.ToolCall] = []
        finish_reason = None
        usage = None
        is_reasoning_started = False
        delimiter = credentials.get("stream_mode_delimiter", "\n\n")
        delimiter = codecs.decode(delimiter, "unicode_escape")

        for chunk in response.iter_lines(decode_unicode=True, delimiter=delimiter):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith(":"):
                continue
            decoded_chunk = chunk.strip().removeprefix("data:").lstrip()
            if decoded_chunk == "[DONE]":
                continue

            try:
                chunk_json: dict = TypeAdapter(dict[str, Any]).validate_json(
                    decoded_chunk
                )
            except ValidationError:
                yield self._create_final_llm_result_chunk(
                    index=chunk_index + 1,
                    message=AssistantPromptMessage(content=""),
                    finish_reason="Non-JSON encountered.",
                    usage=usage,
                    model=model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    full_content=full_assistant_content,
                )
                break

            if chunk_json.get("error") and chunk_json.get("choices") is None:
                raise ValueError(chunk_json.get("error"))

            if u := chunk_json.get("usage"):
                usage = u
            if not chunk_json or len(chunk_json.get("choices", [])) == 0:
                continue

            choice = chunk_json["choices"][0]
            finish_reason = choice.get("finish_reason")
            chunk_index += 1

            if "delta" in choice:
                delta = choice["delta"]
                delta_content, is_reasoning_started = (
                    self._wrap_thinking_by_reasoning_content(
                        delta, is_reasoning_started
                    )
                )

                assistant_message_tool_calls = None
                if (
                    "tool_calls" in delta
                    and credentials.get("function_calling_type", "no_call")
                    == "tool_call"
                ):
                    assistant_message_tool_calls = delta.get("tool_calls", None)
                elif (
                    "function_call" in delta
                    and credentials.get("function_calling_type", "no_call")
                    == "function_call"
                ):
                    assistant_message_tool_calls = [
                        {
                            "id": "tool_call_id",
                            "type": "function",
                            "function": delta.get("function_call", {}),
                        }
                    ]

                if assistant_message_tool_calls:
                    tool_calls = self._extract_response_tool_calls(
                        assistant_message_tool_calls
                    )
                    _increase_tool_call(tool_calls, tools_calls)

                if not delta_content:
                    continue

                assistant_prompt_message = AssistantPromptMessage(content=delta_content)
                if isinstance(delta_content, str):
                    full_assistant_content += delta_content
                else:
                    full_assistant_content += "".join(
                        [c.data for c in delta_content]
                    )
            elif "text" in choice:
                choice_text = choice.get("text", "")
                if choice_text == "":
                    continue
                assistant_prompt_message = AssistantPromptMessage(content=choice_text)
                full_assistant_content += choice_text
            else:
                continue

            yield LLMResultChunk(
                model=model,
                delta=LLMResultChunkDelta(
                    index=chunk_index, message=assistant_prompt_message
                ),
            )

        if tools_calls:
            yield LLMResultChunk(
                model=model,
                delta=LLMResultChunkDelta(
                    index=chunk_index,
                    message=AssistantPromptMessage(tool_calls=tools_calls, content=""),
                ),
            )

        yield self._create_final_llm_result_chunk(
            index=chunk_index,
            message=AssistantPromptMessage(content=""),
            finish_reason=finish_reason,
            usage=usage,
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            full_content=full_assistant_content,
        )
