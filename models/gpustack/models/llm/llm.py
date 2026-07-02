"""GPUStack LLM adapter for OpenAI-compatible inference endpoints."""

import json
import re
from collections.abc import Generator, Iterable
from contextlib import suppress
from typing import Mapping, Optional, Protocol, Union, cast
from urllib.parse import urljoin

import requests
from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    I18nObject,
    ModelFeature,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel


class GPUStackLanguageModel(OAICompatLargeLanguageModel):
    """GPUStack-specific OpenAI-compatible LLM implementation."""

    # Pre-compiled regex for better performance
    _THINK_PATTERN = re.compile(r"^<think>.*?</think>\s*", re.DOTALL)
    # Models that require max_completion_tokens (OpenAI Responses API family)
    _NEEDS_MAX_COMPLETION_TOKENS_PATTERN = re.compile(r"^(o1|o3|gpt-5)", re.IGNORECASE)
    # Timeout for validation requests: (connect_timeout, read_timeout) in seconds
    _VALIDATE_TIMEOUT = (10, 300)

    class _MessageLike(Protocol):
        content: object
        tool_calls: object

    def _wrap_thinking_by_reasoning_content(
        self, delta: dict, is_reasoning: bool
    ) -> tuple[str, bool]:
        # Prefer the new key when present, otherwise fall back to legacy
        reasoning_piece = delta.get("reasoning") or delta.get("reasoning_content")
        content_piece = delta.get("content") or ""

        if reasoning_piece:
            if not is_reasoning:
                # Open a think block on first reasoning token
                output = f"<think>\n{reasoning_piece}"
                is_reasoning = True
            else:
                # Continue streaming inside the think block
                output = str(reasoning_piece)
        elif is_reasoning:
            # No reasoning token in this delta, close the think block
            is_reasoning = False
            output = f"\n</think>{content_piece}"
        else:
            # No reasoning token and not in a reasoning block
            output = content_piece

        return output, is_reasoning

    @staticmethod
    def _needs_max_completion_tokens(m: str) -> bool:
        return bool(GPUStackLanguageModel._NEEDS_MAX_COMPLETION_TOKENS_PATTERN.match(m))

    @staticmethod
    def _raise_credentials_error(response: requests.Response) -> None:
        """Raise a CredentialsValidateFailedError with response details."""
        raise CredentialsValidateFailedError(
            f"Credentials validation failed with status code {response.status_code} "
            f"and response body {response.text}"
        )

    @staticmethod
    def _build_validation_headers(credentials: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        api_key = credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers.update(credentials.get("extra_headers") or {})
        return headers

    @staticmethod
    def _validate_completion_response(
        response: requests.Response, completion_type: LLMMode
    ) -> None:
        if response.status_code != 200:
            GPUStackLanguageModel._raise_credentials_error(response)

        try:
            response_json = response.json()
        except json.JSONDecodeError:
            raise CredentialsValidateFailedError(
                f"Credentials validation failed: JSON decode error, response body {response.text}"
            ) from None

        if completion_type is LLMMode.CHAT:
            expected_object = "chat.completion"
        elif completion_type is LLMMode.COMPLETION:
            expected_object = "text_completion"
        else:
            raise ValueError("Unsupported completion type for model configuration.")

        if response_json.get("object", "") == "":
            response_json["object"] = expected_object

        if response_json.get("object") != expected_object:
            raise CredentialsValidateFailedError(
                f"Credentials validation failed: invalid response object, "
                f"must be '{expected_object}', response body {response.text}"
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
        model = model.strip()

        if model_parameters.get("response_format") == "json_schema":
            json_schema_str = model_parameters.get("json_schema")
            if json_schema_str:
                structured_output_prompt = (
                    "Your response must be a JSON object that validates against "
                    "the following JSON schema, and nothing else.\n"
                    f"JSON Schema: ```json\n{json_schema_str}\n```"
                )
                existing_system_prompt = next(
                    (
                        prompt
                        for prompt in prompt_messages
                        if prompt.role == PromptMessageRole.SYSTEM
                    ),
                    None,
                )
                if existing_system_prompt:
                    existing_system_prompt.content = (
                        structured_output_prompt
                        + "\n\n"
                        + existing_system_prompt.content
                    )
                else:
                    prompt_messages.insert(
                        0, SystemPromptMessage(content=structured_output_prompt)
                    )

        compatible_credentials = self._get_compatible_credentials(credentials)

        # Handle thinking mode based on model support configuration
        agent_thought_support = credentials.get("agent_thought_support", "not_supported")
        enable_thinking_value = None
        if agent_thought_support == "only_thinking_supported":
            # Force enable thinking mode
            enable_thinking_value = True
        elif agent_thought_support == "not_supported":
            # Force disable thinking mode
            enable_thinking_value = False
        else:
            # Both modes supported - use user's preference
            user_enable_thinking = model_parameters.pop("enable_thinking", None)
            if user_enable_thinking is not None:
                enable_thinking_value = bool(user_enable_thinking)

        compatibility_mode = credentials.get("compatibility_mode", "strict")
        # Default to strict mode, only switch to extended if explicitly set
        strict_compatibility_value: bool = compatibility_mode != "extended"

        if enable_thinking_value is not None and strict_compatibility_value is False:
            # Only apply when `strict_compatibility_value` is False since
            # `chat_template_kwargs`, `thinking` and `enable_thinking` are non-standard parameters.

            chat_template_kwargs = model_parameters.setdefault("chat_template_kwargs", {})
            # Support vLLM/SGLang format (chat_template_kwargs)
            chat_template_kwargs["enable_thinking"] = enable_thinking_value
            chat_template_kwargs["thinking"] = enable_thinking_value

            # Support Zhipu AI API format (top-level thinking parameter)
            model_parameters["thinking"] = {
                "type": "enabled" if enable_thinking_value else "disabled"
            }

            # Support top-level `enable_thinking` parameter
            model_parameters["enable_thinking"] = enable_thinking_value

        reasoning_effort_value = model_parameters.pop("reasoning_effort", None)
        if enable_thinking_value is True and reasoning_effort_value is not None:
            # Propagate reasoning_effort to both:
            # - top-level OpenAI Chat Completions param, and
            # - chat_template_kwargs for runtimes that read template kwargs (e.g., llama.cpp).
            # Only apply when thinking mode is explicitly enabled.
            model_parameters["reasoning_effort"] = reasoning_effort_value
            if strict_compatibility_value is False:
                # Only apply when `strict_compatibility_value` is False since
                # `chat_template_kwargs` is a non-standard parameter.
                chat_template_kwargs = model_parameters.setdefault("chat_template_kwargs", {})
                chat_template_kwargs["reasoning_effort"] = reasoning_effort_value

        # Remove thinking content from assistant messages for better performance.
        with suppress(AttributeError, TypeError):
            self._drop_analyze_channel(prompt_messages)

        # Map token parameter name when needed (Responses API style)
        param_pref = credentials.get("token_param_name", "auto")
        token_param_model = compatible_credentials.get("endpoint_model_name") or model
        use_max_completion = (
            (param_pref == "max_completion_tokens")
            or (
                param_pref == "auto"
                and self._needs_max_completion_tokens(token_param_model)
            )
        )

        if use_max_completion:
            # Only map if caller didn't already provide max_completion_tokens
            if "max_completion_tokens" not in model_parameters and "max_tokens" in model_parameters:
                model_parameters["max_completion_tokens"] = model_parameters.pop("max_tokens")

        result = super()._invoke(
            model,
            compatible_credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

        # Filter thinking content from responses if thinking mode is disabled
        # This is necessary for models that don't support server-side thinking control
        if enable_thinking_value is False:
            if stream:
                return self._filter_thinking_stream(result)
            return self._filter_thinking_result(result)

        return result

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """Validate credentials with fallback handling for multiple error scenarios.

        1) When max_completion_tokens is explicitly requested, validate directly
           instead of letting the base class fail with max_tokens first.
        2) If it fails due to too-small token floor on Responses API
           (e.g., "Invalid 'max_output_tokens' ... integer_below_min_value"),
           retry once with a safe minimum of 16 using the appropriate endpoint/param.
        3) If it fails due to thinking/budget_tokens requirements,
           retry with thinking explicitly disabled.
        """
        # When max_completion_tokens is explicitly requested, validate directly
        # instead of letting the base class fail with max_tokens first.
        compatible_credentials = self._get_compatible_credentials(credentials)
        param_pref = compatible_credentials.get("token_param_name", "auto")
        endpoint_model = compatible_credentials.get("endpoint_model_name") or model
        if (
            param_pref == "max_completion_tokens"
            or (param_pref == "auto" and self._needs_max_completion_tokens(endpoint_model))
        ):
            self._retry_with_safe_min_tokens(model, compatible_credentials)
            return None

        try:
            super().validate_credentials(model, compatible_credentials)
            return None
        except CredentialsValidateFailedError as e:
            msg = str(e)

            # --- Retry path 1: token parameter incompatibility ---
            should_retry_floor = (
                "Invalid 'max_output_tokens'" in msg
                or "integer_below_min_value" in msg
            )
            if should_retry_floor:
                self._retry_with_safe_min_tokens(model, compatible_credentials)
                return None

            # --- Retry path 2: thinking / budget_tokens constraints ---
            should_retry_thinking = (
                "budget_tokens" in msg or "thinking" in msg or "reasoning" in msg
            )
            if should_retry_thinking:
                self._retry_with_thinking_disabled(model, compatible_credentials)
                return None

            # Propagate unrelated validation errors
            raise

    def _retry_with_safe_min_tokens(self, model: str, credentials: dict) -> None:
        """Retry validation with a safe minimum token count for Responses API."""
        compatible_credentials = self._get_compatible_credentials(credentials)
        endpoint_model = compatible_credentials.get("endpoint_model_name") or model
        param_pref = compatible_credentials.get("token_param_name", "auto")
        use_max_completion = (
            param_pref == "max_completion_tokens"
            or (param_pref == "auto" and self._needs_max_completion_tokens(endpoint_model))
        )

        safe_min_tokens = 16
        token_field = "max_completion_tokens" if use_max_completion else "max_tokens"
        self._post_validation_request(
            model,
            compatible_credentials,
            payload={token_field: safe_min_tokens},
        )

    def _retry_with_thinking_disabled(self, model: str, credentials: dict) -> None:
        """Retry validation with thinking explicitly disabled for APIs
        that enforce thinking-mode parameters."""
        compatible_credentials = self._get_compatible_credentials(credentials)
        validate_max_tokens = int(
            compatible_credentials.get("validate_credentials_max_tokens", 5) or 5
        )
        self._post_validation_request(
            model,
            compatible_credentials,
            payload={
                "max_tokens": validate_max_tokens,
                "thinking": {"type": "disabled"},
            },
        )

    def _post_validation_request(
        self,
        model: str,
        credentials: dict,
        *,
        payload: dict,
    ) -> None:
        compatible_credentials = self._get_compatible_credentials(credentials)
        endpoint_url = compatible_credentials.get("endpoint_url")
        if not endpoint_url:
            raise CredentialsValidateFailedError("Missing endpoint_url in credentials")
        if not endpoint_url.endswith("/"):
            endpoint_url += "/"

        completion_type = LLMMode.value_of(compatible_credentials["mode"])
        data: dict = {
            "model": compatible_credentials.get("endpoint_model_name", model),
        }
        data.update(payload)

        if completion_type is LLMMode.CHAT:
            data["messages"] = [{"role": "user", "content": "ping"}]
            endpoint_url = urljoin(endpoint_url, "chat/completions")
        elif completion_type is LLMMode.COMPLETION:
            data["prompt"] = "ping"
            endpoint_url = urljoin(endpoint_url, "completions")
        else:
            raise ValueError("Unsupported completion type for model configuration.")

        response: Optional[requests.Response] = None
        try:
            stream_mode_auth = compatible_credentials.get("stream_mode_auth", "not_use")
            if stream_mode_auth == "use":
                data["stream"] = True
                with requests.post(
                    endpoint_url,
                    headers=self._build_validation_headers(compatible_credentials),
                    json=data,
                    timeout=self._VALIDATE_TIMEOUT,
                    stream=True,
                ) as stream_response:
                    if stream_response.status_code != 200:
                        self._raise_credentials_error(stream_response)
                return

            response = requests.post(
                endpoint_url,
                headers=self._build_validation_headers(compatible_credentials),
                json=data,
                timeout=self._VALIDATE_TIMEOUT,
            )
            self._validate_completion_response(response, completion_type)
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            if response is not None:
                raise CredentialsValidateFailedError(
                    f"An error occurred during credentials validation: {ex!s}, "
                    f"response body {response.text}"
                ) from ex
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: {ex!s}"
            ) from ex
        finally:
            if response is not None:
                response.close()

    def _add_custom_parameters(self, credentials: dict) -> None:
        credentials["mode"] = "chat"

    def _get_compatible_credentials(self, credentials: dict) -> dict:
        credentials = credentials.copy()
        base_url = (
            credentials["endpoint_url"]
            .rstrip("/")
            .removesuffix("/v1")
            .removesuffix("/v1-openai")
        )
        credentials["endpoint_url"] = f"{base_url}/v1"
        return credentials

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        entity: AIModelEntity = super().get_customizable_model_schema(
            model, credentials
        )
        features = list(entity.features or [])

        # Configure thinking mode parameter based on model support
        agent_thought_support = credentials.get("agent_thought_support", "not_supported")

        # Add AGENT_THOUGHT feature if thinking mode is supported (either mode)
        if (
            agent_thought_support in ["supported", "only_thinking_supported"]
            and ModelFeature.AGENT_THOUGHT not in features
        ):
            features.append(ModelFeature.AGENT_THOUGHT)
        entity.features = features

        structured_output_support = credentials.get("structured_output_support", "not_supported")
        if structured_output_support == "supported":
            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.RESPONSE_FORMAT.value,
                    label=I18nObject(en_us="Response Format", zh_hans="回复格式"),
                    help=I18nObject(
                        en_us="Specifying the format that the model must output.",
                        zh_hans="指定模型必须输出的格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["text", "json_object", "json_schema"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.JSON_SCHEMA.value,
                    use_template=DefaultParameterName.JSON_SCHEMA.value,
                )
            )

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_us=credentials["display_name"],
                zh_hans=credentials["display_name"],
            )

        # Only add the enable_thinking parameter if the model supports both modes
        # If only_thinking_supported, the parameter is not needed (forced behavior)
        if agent_thought_support == "supported":
            entity.parameter_rules.append(
                ParameterRule(
                    name="enable_thinking",
                    label=I18nObject(en_us="Thinking mode", zh_hans="思考模式"),
                    help=I18nObject(
                        en_us=(
                            "Whether to enable thinking mode, applicable to various "
                            "thinking mode models deployed on reasoning frameworks "
                            "such as vLLM and SGLang, for example Qwen3."
                        ),
                        zh_hans="是否开启思考模式，适用于vLLM和SGLang等推理框架部署的多种思考模式模型，例如Qwen3。",
                    ),
                    type=ParameterType.BOOLEAN,
                    required=False,
                )
            )

        if agent_thought_support in ["supported", "only_thinking_supported"]:
            entity.parameter_rules.append(
                ParameterRule(
                    name="reasoning_format",
                    label=I18nObject(en_us="Reasoning Format", zh_hans="推理格式"),
                    help=I18nObject(
                        en_us="Specifying the format that the model must output reasoning.",
                        zh_hans="指定模型必须输出的推理格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["none", "auto", "deepseek", "deepseek-legacy"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(en_us="Reasoning effort", zh_hans="推理工作"),
                    help=I18nObject(
                        en_us="Constrains effort on reasoning for reasoning models.",
                        zh_hans="限制推理模型的推理工作。",
                    ),
                    type=ParameterType.STRING,
                    options=["low", "medium", "high"],
                    required=False,
                )
            )

        return entity

    @classmethod
    def _drop_analyze_channel(cls, prompt_messages: list[PromptMessage]) -> None:
        """
        Remove thinking content from assistant messages for better performance.

        Uses early exit and pre-compiled regex to minimize overhead.
        """
        for p in prompt_messages:
            # Early exit conditions
            if not isinstance(p, AssistantPromptMessage):
                continue
            if not isinstance(p.content, str):
                continue
            # Quick check to avoid regex if not needed
            if not p.content.startswith("<think>"):
                continue

            # Only perform regex substitution when necessary
            new_content = cls._THINK_PATTERN.sub("", p.content, count=1)
            # Only update if changed
            if new_content != p.content:
                p.content = new_content

    def _filter_thinking_result(self, result: LLMResult) -> LLMResult:
        """Filter thinking content from non-streaming result"""
        if result.message and result.message.content:
            content = result.message.content
            if isinstance(content, str) and content.startswith("<think>"):
                filtered_content = self._THINK_PATTERN.sub("", content, count=1)
                if filtered_content != content:
                    result.message.content = filtered_content
        return result

    @staticmethod
    def _trailing_partial_tag_length(text: str, tag: str) -> int:
        max_prefix_len = min(len(text), len(tag) - 1)
        for prefix_len in range(max_prefix_len, 0, -1):
            if text.endswith(tag[:prefix_len]):
                return prefix_len
        return 0

    @staticmethod
    def _get_chunk_message(
        chunk: object,
    ) -> "GPUStackLanguageModel._MessageLike | None":
        message = getattr(chunk, "message", None)
        if message is not None and hasattr(message, "content"):
            return cast("GPUStackLanguageModel._MessageLike", message)

        delta = getattr(chunk, "delta", None)
        if delta is not None:
            delta_message = getattr(delta, "message", None)
            if delta_message is not None and hasattr(delta_message, "content"):
                return cast("GPUStackLanguageModel._MessageLike", delta_message)

        return None

    @staticmethod
    def _chunk_has_terminal_metadata(chunk: object) -> bool:
        if getattr(chunk, "usage", None) is not None:
            return True
        if getattr(chunk, "finish_reason", None) is not None:
            return True

        delta = getattr(chunk, "delta", None)
        if delta is not None:
            if getattr(delta, "finish_reason", None) is not None:
                return True
            if getattr(delta, "usage", None) is not None:
                return True

        message = GPUStackLanguageModel._get_chunk_message(chunk)
        if message is not None and getattr(message, "tool_calls", None):
            return True
        return False

    def _filter_thinking_stream(self, stream: Iterable[object]) -> Generator:
        """Filter thinking content from streaming result"""
        open_tag = "<think>"
        close_tag = "</think>"
        buffer = ""
        in_thinking = False
        buffered_chunk = None

        for chunk in stream:
            message = self._get_chunk_message(chunk)
            content = getattr(message, "content", None) if message is not None else None

            if isinstance(content, str) and content:
                buffer += content
                buffered_chunk = chunk
                output_parts: list[str] = []

                while buffer:
                    if in_thinking:
                        close_idx = buffer.find(close_tag)
                        if close_idx != -1:
                            buffer = buffer[close_idx + len(close_tag):]
                            in_thinking = False
                            continue

                        keep_len = self._trailing_partial_tag_length(buffer, close_tag)
                        buffer = buffer[-keep_len:] if keep_len else ""
                        break

                    open_idx = buffer.find(open_tag)
                    if open_idx != -1:
                        if open_idx > 0:
                            output_parts.append(buffer[:open_idx])
                        buffer = buffer[open_idx + len(open_tag):]
                        in_thinking = True
                        continue

                    keep_len = self._trailing_partial_tag_length(buffer, open_tag)
                    if keep_len:
                        output_parts.append(buffer[:-keep_len])
                        buffer = buffer[-keep_len:]
                    else:
                        output_parts.append(buffer)
                        buffer = ""
                    break

                output = "".join(output_parts)
                if output or self._chunk_has_terminal_metadata(chunk):
                    if message is not None:
                        message.content = output
                        yield chunk
                        buffered_chunk = None
            else:
                # Yield chunks without content as-is
                yield chunk

        if buffer and not in_thinking and buffered_chunk is not None:
            buffered_message = self._get_chunk_message(buffered_chunk)
            if buffered_message is not None:
                buffered_message.content = buffer
                yield buffered_chunk

    @staticmethod
    def _extract_response_message(
        output: dict,
        completion_type: LLMMode,
        function_calling_type: str,
    ) -> tuple[str, object]:
        if completion_type is LLMMode.CHAT:
            message = output.get("message") or {}
            raw_content = message.get("content")
            if isinstance(raw_content, str):
                response_content = raw_content
            elif raw_content is None:
                response_content = ""
            else:
                response_content = str(raw_content)

            if function_calling_type == "tool_call":
                return response_content, message.get("tool_calls")
            if function_calling_type == "function_call":
                return response_content, message.get("function_call")
            return response_content, None

        raw_text = output.get("text", "")
        response_content = raw_text if isinstance(raw_text, str) else str(raw_text or "")
        return response_content, None

    def _build_response_tool_calls(
        self, tool_calls: object, function_calling_type: str
    ) -> list:
        if not tool_calls:
            return []
        if function_calling_type == "tool_call":
            return self._extract_response_tool_calls(tool_calls)
        if function_calling_type == "function_call":
            function_call = self._extract_response_function_call(tool_calls)
            return [function_call] if function_call else []
        return []

    def _build_assistant_message(
        self,
        output: dict,
        completion_type: LLMMode,
        function_calling_type: str,
    ) -> AssistantPromptMessage:
        response_content, tool_calls = self._extract_response_message(
            output, completion_type, function_calling_type
        )
        assistant_message = AssistantPromptMessage(content=response_content, tool_calls=[])
        assistant_message.tool_calls = self._build_response_tool_calls(
            tool_calls, function_calling_type
        )
        return assistant_message

    def _calculate_completion_tokens(
        self,
        response_json: dict,
        prompt_messages: list[PromptMessage],
        assistant_message: AssistantPromptMessage,
        credentials: dict,
    ) -> tuple[int, int]:
        usage = response_json.get("usage")
        if usage:
            return usage["prompt_tokens"], usage["completion_tokens"]

        prompt_tokens = self._num_tokens_from_messages(
            prompt_messages, credentials=credentials
        )
        completion_tokens = self._num_tokens_from_string(
            assistant_message.content or ""
        )
        return prompt_tokens, completion_tokens

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        response_json: dict = response.json()
        completion_type = LLMMode.value_of(credentials["mode"])
        choices = response_json.get("choices") or []
        if not choices:
            raise InvokeError("LLM response returned no choices")

        function_calling_type = credentials.get("function_calling_type", "no_call")
        assistant_message = self._build_assistant_message(
            choices[0], completion_type, function_calling_type
        )
        prompt_tokens, completion_tokens = self._calculate_completion_tokens(
            response_json, prompt_messages, assistant_message, credentials
        )

        return LLMResult(
            id=response_json.get("id"),
            model=response_json.get("model", model),
            message=assistant_message,
            usage=self._calc_response_usage(
                model, credentials, prompt_tokens, completion_tokens
            ),
        )
