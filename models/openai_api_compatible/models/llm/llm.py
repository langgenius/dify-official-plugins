import json
import re
from contextlib import suppress
from typing import Mapping, Optional, Union, Generator, List
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
    PromptMessage,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
    AssistantPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

from openai import OpenAI


class OpenAILargeLanguageModel(OAICompatLargeLanguageModel):
    # Pre-compiled regex for better performance
    _THINK_PATTERN = re.compile(r"^<think>.*?</think>\s*", re.DOTALL)
    # Models that require max_completion_tokens (OpenAI Responses API family)
    _NEEDS_MAX_COMPLETION_TOKENS_PATTERN = re.compile(r"^(o1|o3|gpt-5)", re.IGNORECASE)

    def _wrap_thinking_by_reasoning_content(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        Override base wrapper to support both legacy 'reasoning_content' and
        newer 'reasoning' fields (e.g., vLLM >= 0.17.1), emitting <think> blocks
        compatible with Dify's downstream filters.
        """
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

    # Timeout for validation requests: (connect_timeout, read_timeout) in seconds
    _VALIDATE_TIMEOUT = (10, 300)

    @staticmethod
    def _needs_max_completion_tokens(m: str) -> bool:
        return bool(OpenAILargeLanguageModel._NEEDS_MAX_COMPLETION_TOKENS_PATTERN.match(m))

    @staticmethod
    def _raise_credentials_error(response: requests.Response) -> None:
        """Raise a CredentialsValidateFailedError with response details."""
        raise CredentialsValidateFailedError(
            f"Credentials validation failed with status code {response.status_code} "
            f"and response body {response.text}"
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """Validate credentials with fallback handling for multiple error scenarios.

        1) Try base validation first (keeps upstream compatibility).
        2) If it fails due to too-small token floor on Responses API
           (e.g., "Invalid 'max_output_tokens' ... integer_below_min_value"),
           retry once with a safe minimum of 16 using the appropriate endpoint/param.
        3) If it fails due to thinking/budget_tokens requirements
           (e.g., Poe API requiring budget_tokens for Claude models),
           retry with thinking explicitly disabled.
        """
        # When max_completion_tokens is explicitly requested, validate directly
        # instead of letting the base class fail with max_tokens first.
        param_pref = credentials.get("token_param_name", "auto")
        endpoint_model = credentials.get("endpoint_model_name") or model
        if (
            param_pref == "max_completion_tokens"
            or (param_pref == "auto" and self._needs_max_completion_tokens(endpoint_model))
        ):
            self._retry_with_safe_min_tokens(model, credentials)
            return

        try:
            return super().validate_credentials(model, credentials)
        except CredentialsValidateFailedError as e:
            msg = str(e)

            # --- Retry path 1: token parameter incompatibility ---
            should_retry_floor = (
                "Invalid 'max_output_tokens'" in msg
                or "integer_below_min_value" in msg
            )
            if should_retry_floor:
                self._retry_with_safe_min_tokens(model, credentials)
                return

            # --- Retry path 2: thinking / budget_tokens constraints ---
            should_retry_thinking = (
                "budget_tokens" in msg or "thinking" in msg
            )
            if should_retry_thinking:
                self._retry_with_thinking_disabled(model, credentials)
                return

            # Propagate unrelated validation errors
            raise

    def _retry_with_safe_min_tokens(self, model: str, credentials: dict) -> None:
        """Retry validation with a safe minimum token count for Responses API."""
        endpoint_url = credentials.get("endpoint_url")
        if not endpoint_url:
            raise CredentialsValidateFailedError("Missing endpoint_url in credentials")

        api_key = credentials.get("api_key")
        extra_headers = credentials.get("extra_headers") or {}
        client = OpenAI(api_key=api_key, base_url=endpoint_url, default_headers=extra_headers)

        endpoint_model = credentials.get("endpoint_model_name") or model
        mode = credentials.get("mode", "chat")

        param_pref = credentials.get("token_param_name", "auto")
        use_max_completion = (
            param_pref == "max_completion_tokens"
            or (param_pref == "auto" and self._needs_max_completion_tokens(endpoint_model))
        )

        SAFE_MIN_TOKENS = 16

        try:
            if mode == "chat":
                if use_max_completion:
                    client.chat.completions.create(
                        model=endpoint_model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_completion_tokens=SAFE_MIN_TOKENS,
                        stream=False,
                    )
                else:
                    client.chat.completions.create(
                        model=endpoint_model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=SAFE_MIN_TOKENS,
                        stream=False,
                    )
            else:
                client.completions.create(
                    model=endpoint_model,
                    prompt="ping",
                    max_tokens=SAFE_MIN_TOKENS,
                    stream=False,
                )
        except Exception as sub_e:
            raise CredentialsValidateFailedError(str(sub_e)) from sub_e

    def _retry_with_thinking_disabled(self, model: str, credentials: dict) -> None:
        """Retry validation with thinking explicitly disabled for APIs
        that enforce thinking-mode parameters (e.g., Poe API)."""
        headers = {"Content-Type": "application/json"}

        api_key = credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        endpoint_url = credentials["endpoint_url"]
        if not endpoint_url.endswith("/"):
            endpoint_url += "/"

        # The `or 5` fallback handles cases where the credential value is set
        # but empty (e.g., "" or None from user input).
        validate_max_tokens = int(credentials.get("validate_credentials_max_tokens", 5) or 5)
        data: dict = {
            "model": credentials.get("endpoint_model_name", model),
            "max_tokens": validate_max_tokens,
            "thinking": {"type": "disabled"},
        }

        completion_type = LLMMode.value_of(credentials["mode"])

        if completion_type is LLMMode.CHAT:
            data["messages"] = [{"role": "user", "content": "ping"}]
            endpoint_url = urljoin(endpoint_url, "chat/completions")
        elif completion_type is LLMMode.COMPLETION:
            data["prompt"] = "ping"
            endpoint_url = urljoin(endpoint_url, "completions")
        else:
            raise ValueError("Unsupported completion type for model configuration.")

        try:
            response = requests.post(
                endpoint_url, headers=headers, json=data,
                timeout=self._VALIDATE_TIMEOUT,
            )
            if response.status_code != 200:
                self._raise_credentials_error(response)
        except CredentialsValidateFailedError:
            raise
        except Exception as ex:
            raise CredentialsValidateFailedError(
                f"An error occurred during credentials validation: {ex!s}"
            ) from ex

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)

        structured_output_support = credentials.get("structured_output_support", "not_supported")
        if structured_output_support == "supported":
            # ----
            # The following section should be added after the new version of `dify-plugin-sdks`
            # is released.
            # Related Commit:
            # https://github.com/langgenius/dify-plugin-sdks/commit/0690573a879caf43f92494bf411f45a1835d96f6
            # ----
            # try:
            #     entity.features.index(ModelFeature.STRUCTURED_OUTPUT)
            # except ValueError:
            #     entity.features.append(ModelFeature.STRUCTURED_OUTPUT)

            entity.parameter_rules.append(
                ParameterRule(
                    name=DefaultParameterName.RESPONSE_FORMAT.value,
                    label=I18nObject(en_US="Response Format", zh_Hans="回复格式"),
                    help=I18nObject(
                        en_US="Specifying the format that the model must output.",
                        zh_Hans="指定模型必须输出的回复格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["text", "json_object", "json_schema"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="reasoning_format",
                    label=I18nObject(en_US="Reasoning Format", zh_Hans="推理格式"),
                    help=I18nObject(
                        en_US="Specifying the format that the model must output reasoning.",
                        zh_Hans="指定模型必须输出的推理格式。",
                    ),
                    type=ParameterType.STRING,
                    options=["none", "auto", "deepseek", "deepseek-legacy"],
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
                en_US=credentials["display_name"], zh_Hans=credentials["display_name"]
            )

        # Configure thinking mode parameter based on model support
        agent_thought_support = credentials.get("agent_thought_support", "not_supported")
        
        # Add AGENT_THOUGHT feature if thinking mode is supported (either mode)
        if agent_thought_support in ["supported", "only_thinking_supported"] and ModelFeature.AGENT_THOUGHT not in entity.features:
            entity.features.append(ModelFeature.AGENT_THOUGHT)
        
        # Only add the enable_thinking parameter if the model supports both modes
        # If only_thinking_supported, the parameter is not needed (forced behavior)
        if agent_thought_support == "supported":
            entity.parameter_rules.append(
                ParameterRule(
                    name="enable_thinking",
                    label=I18nObject(en_US="Thinking mode", zh_Hans="思考模式"),
                    help=I18nObject(
                        en_US="Whether to enable thinking mode, applicable to various thinking mode models deployed on reasoning frameworks such as vLLM and SGLang, for example Qwen3.",
                        zh_Hans="是否开启思考模式，适用于vLLM和SGLang等推理框架部署的多种思考模式模型，例如Qwen3。",
                    ),
                    type=ParameterType.BOOLEAN,
                    required=False,
                )
            )

        if agent_thought_support in ["supported", "only_thinking_supported"]:
            entity.parameter_rules.append(
                ParameterRule(
                    name="reasoning_effort",
                    label=I18nObject(en_US="Reasoning effort", zh_Hans="推理工作"),
                    help=I18nObject(
                        en_US="Constrains effort on reasoning for reasoning models.",
                        zh_Hans="限制推理模型的推理工作。",
                    ),
                    type=ParameterType.STRING,
                    options=["low", "medium", "high"],
                    required=False,
                )
            )
        
        return entity

    @classmethod
    def _drop_analyze_channel(cls, prompt_messages: List[PromptMessage]) -> None:
        """
        Remove thinking content from assistant messages for better performance.

        Uses early exit and pre-compiled regex to minimize overhead.
        Args:
            prompt_messages:

        Returns:

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
        # Compatibility adapter for Dify's 'json_schema' structured output mode.
        # The base class does not natively handle the 'json_schema' parameter. This block
        # translates it into a standard OpenAI-compatible request by:
        # 1. Injecting the JSON schema directly into the system prompt to guide the model.
        # This ensures models like gpt-4o produce the correct structured output.
        if model_parameters.get("response_format") == "json_schema":
            # Use .get() instead of .pop() for safety
            json_schema_str = model_parameters.get("json_schema")

            if json_schema_str:
                structured_output_prompt = (
                    "Your response must be a JSON object that validates against the following JSON schema, and nothing else.\n"
                    f"JSON Schema: ```json\n{json_schema_str}\n```"
                )

                existing_system_prompt = next(
                    (p for p in prompt_messages if p.role == PromptMessageRole.SYSTEM), None
                )
                if existing_system_prompt:
                    existing_system_prompt.content = (
                        structured_output_prompt + "\n\n" + existing_system_prompt.content
                    )
                else:
                    prompt_messages.insert(0, SystemPromptMessage(content=structured_output_prompt))

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
            # `chat_template_kwargs` , `thinking` and `enable_thinking` are non-standard parameters.

            chat_template_kwargs = model_parameters.setdefault("chat_template_kwargs", {})
            # Support vLLM/SGLang format (chat_template_kwargs)
            chat_template_kwargs["enable_thinking"] = enable_thinking_value
            chat_template_kwargs["thinking"] = enable_thinking_value

            # Support Zhipu AI API format (top-level thinking parameter)
            # This allows compatibility with Zhipu's official API format: {"thinking": {"type": "enabled/disabled"}}
            model_parameters["thinking"] = {
                "type": "enabled" if enable_thinking_value else "disabled"
            }

            # Support top-level `enable_thinking` parameter
            # This allows compatibility API format: {"enable_thinking": False/True}
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
        with suppress(Exception):
            self._drop_analyze_channel(prompt_messages)

        # Map token parameter name when needed (Responses API style)
        param_pref = credentials.get("token_param_name", "auto")

        def _needs_max_completion_tokens(m: str) -> bool:
            return bool(re.match(r"^(o1|o3|gpt-5)", m, re.IGNORECASE))

        use_max_completion = (
            (param_pref == "max_completion_tokens")
            or (param_pref == "auto" and _needs_max_completion_tokens(model))
        )

        if use_max_completion:
            # Only map if caller didn't already provide max_completion_tokens
            if "max_completion_tokens" not in model_parameters and "max_tokens" in model_parameters:
                model_parameters["max_completion_tokens"] = model_parameters.pop("max_tokens")

        result = super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

        # Filter thinking content from responses if thinking mode is disabled
        # This is necessary for models like Minimax M2.1 that don't support server-side thinking control
        if enable_thinking_value is False:
            if stream:
                return self._filter_thinking_stream(result)
            else:
                return self._filter_thinking_result(result)
        
        return result

    def _filter_thinking_result(self, result: LLMResult) -> LLMResult:
        """Filter thinking content from non-streaming result"""
        if result.message and result.message.content:
            content = result.message.content
            if isinstance(content, str) and content.startswith("<think>"):
                filtered_content = self._THINK_PATTERN.sub("", content, count=1)
                if filtered_content != content:
                    result.message.content = filtered_content
        return result

    def _filter_thinking_stream(self, stream: Generator) -> Generator:
        """Filter thinking content from streaming result"""
        buffer = ""
        in_thinking = False
        thinking_started = False
        
        for chunk in stream:
            if chunk.delta and chunk.delta.message and chunk.delta.message.content:
                content = chunk.delta.message.content
                buffer += content
                
                # Detect start of thinking block
                if not thinking_started and buffer.startswith("<think>"):
                    in_thinking = True
                    thinking_started = True
                    # Don't continue here - check for end tag in same iteration
                
                # Detect end of thinking block
                if in_thinking and "</think>" in buffer:
                    # Find the end of thinking block
                    end_idx = buffer.find("</think>") + len("</think>")
                    # Skip whitespace after </think>
                    while end_idx < len(buffer) and buffer[end_idx].isspace():
                        end_idx += 1
                    # Remove thinking block and continue with remaining content
                    buffer = buffer[end_idx:]
                    in_thinking = False
                    thinking_started = False
                    # Yield remaining content if any
                    if buffer:
                        chunk.delta.message.content = buffer
                        buffer = ""
                        yield chunk
                    continue
                
                # If not in thinking block, yield content
                if not in_thinking:
                    yield chunk
                    buffer = ""
            else:
                # Yield chunks without content as-is
                yield chunk
