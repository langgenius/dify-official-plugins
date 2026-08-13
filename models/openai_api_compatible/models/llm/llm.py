import json
import re
from contextlib import suppress
from typing import Mapping, Optional, Union, Generator, List, Any
from urllib.parse import urljoin, urlparse

import requests
from dify_plugin.entities.model import (
    AIModelEntity,
    DefaultParameterName,
    I18nObject,
    ModelFeature,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import (
    LLMMode,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
    AssistantPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
    TextPromptMessageContent,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

from openai import OpenAI


class OpenAILargeLanguageModel(OAICompatLargeLanguageModel):
    # Pre-compiled regex for better performance
    _THINK_PATTERN = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
    # Models that require max_completion_tokens (OpenAI Responses API family)
    _NEEDS_MAX_COMPLETION_TOKENS_PATTERN = re.compile(r"^(o1|o3|gpt-5)", re.IGNORECASE)

    def _wrap_thinking_by_reasoning_content(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        Override base wrapper to support both legacy 'reasoning_content' and
        newer 'reasoning' fields (e.g., vLLM >= 0.17.1), emitting <think> blocks
        compatible with Dify's downstream filters.
        """
        # Prefer the new key when present, otherwise fall back to legacy
        reasoning_piece = delta.get("reasoning") or delta.get("reasoning_content") or ""
        content_piece = delta.get("content") or ""
        output = ""
        if len(reasoning_piece) > 0:
            if not is_reasoning:
                # Open a think block on first reasoning token
                output += f"<think>\n{reasoning_piece}"
                is_reasoning = True
            else:
                # Continue streaming inside the think block
                output += str(reasoning_piece)

        if is_reasoning:
            # delta without reasoning/content should just close the block
            if len(reasoning_piece) == 0 and len(content_piece) == 0:
                is_reasoning = False
                output += f"\n</think>"
            # sometimes reasoning_piece is not empty and content_piece is not empty. but if content_piece is not empty, then we should not close the think block
            if len(content_piece) > 0:
                is_reasoning = False
                output += f"\n</think>{content_piece}"
        elif len(content_piece) > 0:
            output += content_piece

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
                    label=I18nObject(en_us="Response Format", zh_hans="回复格式"),
                    help=I18nObject(
                        en_us="Specifying the format that the model must output.",
                        zh_hans="指定模型必须输出的回复格式。",
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
                en_us=credentials["display_name"], zh_hans=credentials["display_name"]
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
                    label=I18nObject(en_us="Thinking mode", zh_hans="思考模式"),
                    help=I18nObject(
                        en_us="Whether to enable thinking mode, applicable to various thinking mode models deployed on reasoning frameworks such as vLLM and SGLang, for example Qwen3.",
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
                        en_us="Specifies the format in which the model must output reasoning.",
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

        # Configure web search parameter if supported
        web_search_support = credentials.get("web_search_support", "not_supported")
        if web_search_support != "not_supported":
            entity.parameter_rules.append(
                ParameterRule(
                    name="web_search",
                    label=I18nObject(en_us="Web Search", zh_hans="联网搜索"),
                    help=I18nObject(
                        en_us="Whether to enable web search. When enabled, the model will search the internet for relevant information to generate responses.",
                        zh_hans="是否启用联网搜索。启用后，模型将搜索互联网以获取相关信息来生成回复。",
                    ),
                    type=ParameterType.BOOLEAN,
                    required=False,
                    default=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="web_search_allowed_domains",
                    label=I18nObject(en_us="Allowed Domains", zh_hans="允许的搜索域名"),
                    help=I18nObject(
                        en_us="Comma or newline-separated list of allowed domains for web search results (e.g., openai.com, github.com). Max 100 domains. Requires Responses API.",
                        zh_hans="允许的搜索域名列表，支持逗号或换行分隔（例如 openai.com, github.com）。最多 100 个域名。需要 Responses API。",
                    ),
                    type=ParameterType.STRING,
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="web_search_blocked_domains",
                    label=I18nObject(en_us="Blocked Domains", zh_hans="屏蔽的搜索域名"),
                    help=I18nObject(
                        en_us="Comma or newline-separated list of blocked domains for web search results (e.g., reddit.com, quora.com). Max 100 domains. Requires Responses API.",
                        zh_hans="屏蔽的搜索域名列表，支持逗号或换行分隔（例如 reddit.com, quora.com）。最多 100 个域名。需要 Responses API。",
                    ),
                    type=ParameterType.STRING,
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="web_search_context_size",
                    label=I18nObject(en_us="Search Context Size", zh_hans="搜索上下文大小"),
                    help=I18nObject(
                        en_us="Controls amount of web search result context provided to model ('low', 'medium', 'high'). Requires Responses API.",
                        zh_hans="控制提供给模型的网络搜索结果上下文量（'low', 'medium', 'high'）。需要 Responses API。",
                    ),
                    type=ParameterType.STRING,
                    options=["medium", "low", "high"],
                    required=False,
                )
            )
            entity.parameter_rules.append(
                ParameterRule(
                    name="web_search_user_country",
                    label=I18nObject(en_us="Search User Country", zh_hans="搜索用户国家/地区"),
                    help=I18nObject(
                        en_us="Optional 2-letter ISO country code (e.g., US, JP) to refine search location. Requires Responses API.",
                        zh_hans="可选的 2 位 ISO 国家/地区代码（例如 US、JP）以优化搜索地理位置。需要 Responses API。",
                    ),
                    type=ParameterType.STRING,
                    required=False,
                )
            )

        # Register VIDEO/AUDIO/DOCUMENT features when the corresponding credential is enabled.
        # Without these on entity.features, Dify host filters out non-image attachments
        # before they reach _convert_prompt_message_to_dict, causing silent drop.
        for credential_key, feature in (
            ("video_support", ModelFeature.VIDEO),
            ("audio_support", ModelFeature.AUDIO),
            ("document_support", ModelFeature.DOCUMENT),
        ):
            if credentials.get(credential_key, "no_support") == "support" and feature not in entity.features:
                entity.features.append(feature)

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
            if "<think>" not in p.content:
                continue

            # Only perform regex substitution when necessary
            new_content = cls._THINK_PATTERN.sub("", p.content)
            # Only update if changed
            if new_content != p.content:
                p.content = new_content

    def _convert_prompt_message_to_dict(
        self, message: PromptMessage, credentials: Optional[dict] = None
    ) -> dict:
        # The base SDK implementation only handles TEXT and IMAGE content for user
        # messages, silently dropping VIDEO / AUDIO / DOCUMENT. Extend it so the same
        # OpenAI-compatible request shape carries the additional modalities. The
        # encoding follows what LiteLLM and OpenAI-compatible aggregators accept:
        #   - VIDEO/AUDIO: image_url with a data URI (mime_type carried in the URI),
        #     which providers like Vertex Gemini convert into inline_data.
        #   - DOCUMENT: the OpenAI Files-compatible "file" part with file_data set
        #     to the data URI.
        if isinstance(message, UserPromptMessage) and isinstance(message.content, list):
            sub_messages: list[dict] = []
            for c in message.content:
                if c.type == PromptMessageContentType.TEXT:
                    sub_messages.append({"type": "text", "text": c.data})
                elif c.type == PromptMessageContentType.IMAGE:
                    image_c: ImagePromptMessageContent = c
                    sub_messages.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_c.data,
                                "detail": image_c.detail.value,
                            },
                        }
                    )
                elif c.type == PromptMessageContentType.VIDEO:
                    video_c: VideoPromptMessageContent = c
                    sub_messages.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": video_c.data},
                        }
                    )
                elif c.type == PromptMessageContentType.AUDIO:
                    audio_c: AudioPromptMessageContent = c
                    sub_messages.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": audio_c.data},
                        }
                    )
                elif c.type == PromptMessageContentType.DOCUMENT:
                    doc_c: DocumentPromptMessageContent = c
                    sub_messages.append(
                        {
                            "type": "file",
                            "file": {
                                "file_data": doc_c.data,
                                "filename": doc_c.filename or "document",
                            },
                        }
                    )
            message_dict: dict = {"role": "user", "content": sub_messages}
            if message.name:
                message_dict["name"] = message.name
            return message_dict
        return super()._convert_prompt_message_to_dict(message, credentials)

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
        if credentials.get("api_type") == "responses":
            return self._chat_generate_with_responses(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
            )

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

        reasoning_format_value = model_parameters.pop("reasoning_format", None)
        if reasoning_format_value is not None and strict_compatibility_value is False:
            model_parameters["reasoning_format"] = reasoning_format_value

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
        
        # Handle web search based on credential configuration
        web_search_support = credentials.get("web_search_support", "not_supported")
        enable_web_search = model_parameters.pop("web_search", False)
        if enable_web_search and web_search_support != "not_supported":
            if web_search_support == "tool_standard":
                # Standard tools format: {"type": "web_search", "web_search": {"enable": true}}
                # Used by ZhipuAI, Baichuan, etc.
                web_search_tool = {
                    "type": "web_search",
                    "web_search": {"enable": True},
                }
                if "tools" in model_parameters:
                    model_parameters["tools"].append(web_search_tool)
                else:
                    model_parameters["tools"] = [web_search_tool]
            elif web_search_support == "tool_simple":
                # Simple tools format: {"type": "web_search"}
                # Used by Volcengine, etc.
                web_search_tool = {"type": "web_search"}
                if "tools" in model_parameters:
                    model_parameters["tools"].append(web_search_tool)
                else:
                    model_parameters["tools"] = [web_search_tool]
            elif web_search_support == "parameter":
                # Parameter format: top-level web_search parameter
                model_parameters["web_search"] = True

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

        # The base SDK adds a top-level "user" to the request body whenever user is truthy.
        # Some OpenAI-compatible gateways reject that optional parameter outright, so allow
        # the credential to suppress it. Default keeps today's behaviour: user is still sent.
        if credentials.get("user_identity_support", "support") == "no_support":
            user = None

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
            if isinstance(content, str) and "<think>" in content:
                filtered_content = self._THINK_PATTERN.sub("", content)
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

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        """
        Handle non-streaming chat responses that omit `message.content` when returning tool calls.

        Some OpenAI-compatible gateways, including LiteLLM-backed Azure deployments, may
        legitimately return tool calls without a `content` field. The SDK base class indexes
        `message["content"]` directly, which raises `KeyError('content')` in that case.
        """
        response_json: dict = response.json()
        completion_type = LLMMode.value_of(credentials["mode"])
        choices = response_json.get("choices") or []
        if not choices:
            raise InvokeError("LLM response returned no choices")

        output = choices[0]
        message_id = response_json.get("id")

        response_content = ""
        tool_calls = None
        function_calling_type = credentials.get("function_calling_type", "no_call")

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
                tool_calls = message.get("tool_calls")
            elif function_calling_type == "function_call":
                tool_calls = message.get("function_call")
        elif completion_type is LLMMode.COMPLETION:
            raw_text = output.get("text", "")
            response_content = raw_text if isinstance(raw_text, str) else str(raw_text or "")

        assistant_message = AssistantPromptMessage(content=response_content, tool_calls=[])

        if tool_calls:
            if function_calling_type == "tool_call":
                assistant_message.tool_calls = self._extract_response_tool_calls(tool_calls)
            elif function_calling_type == "function_call":
                function_call = self._extract_response_function_call(tool_calls)
                assistant_message.tool_calls = [function_call] if function_call else []

        usage = response_json.get("usage")
        if usage:
            prompt_tokens = usage["prompt_tokens"]
            completion_tokens = usage["completion_tokens"]
        else:
            prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
            completion_tokens = self._num_tokens_from_string(assistant_message.content or "")

        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        return LLMResult(
            id=message_id,
            model=response_json.get("model", model),
            message=assistant_message,
            usage=usage,
        )

    def _create_openai_client(self, credentials: dict) -> OpenAI:
        api_key = credentials.get("api_key") or "dummy"
        endpoint_url = credentials.get("endpoint_url")
        base_url = None
        if endpoint_url:
            base_url = endpoint_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url += "/v1"
        extra_headers = credentials.get("extra_headers") or None
        return OpenAI(api_key=api_key, base_url=base_url, default_headers=extra_headers)

    @staticmethod
    def _normalize_domains(raw_domains: Any) -> list[str]:
        if raw_domains is None:
            return []
        if isinstance(raw_domains, str):
            candidates = re.split(r"[\s,\n\r]+", raw_domains)
        elif isinstance(raw_domains, (list, tuple)):
            candidates = [str(item) for item in raw_domains]
        else:
            candidates = [str(raw_domains)]

        normalized_domains: list[str] = []
        seen_domains: set[str] = set()

        for candidate in candidates:
            token = candidate.strip()
            if not token:
                continue

            parsed = urlparse(token if "://" in token else f"https://{token}")
            host = parsed.netloc or parsed.path
            host = host.strip().lower().rstrip(".")
            if ":" in host:
                host = host.split(":", 1)[0]

            if not host:
                continue
            if not re.fullmatch(r"[a-z0-9.-]+", host):
                continue

            if host not in seen_domains:
                seen_domains.add(host)
                normalized_domains.append(host)

        return normalized_domains[:100]

    def _extract_responses_web_search_config(
        self, model_parameters: dict, credentials: dict
    ) -> Optional[dict[str, Any]]:
        web_search_support = credentials.get("web_search_support", "not_supported")
        enable_web_search = model_parameters.pop("web_search", False)
        allowed_domains = model_parameters.pop("web_search_allowed_domains", None)
        blocked_domains = model_parameters.pop("web_search_blocked_domains", None)
        context_size = model_parameters.pop("web_search_context_size", None)
        country = model_parameters.pop("web_search_user_country", None)

        if not enable_web_search or web_search_support == "not_supported":
            return None

        web_search_tool: dict[str, Any] = {"type": "web_search"}

        filters: dict[str, Any] = {}
        norm_allowed = self._normalize_domains(allowed_domains)
        norm_blocked = self._normalize_domains(blocked_domains)
        if norm_allowed:
            filters["allowed_domains"] = norm_allowed
        if norm_blocked:
            filters["blocked_domains"] = norm_blocked

        if filters:
            web_search_tool["filters"] = filters

        if context_size:
            web_search_tool["search_context_size"] = context_size

        if country:
            country_code = str(country).strip().upper()
            if re.fullmatch(r"[A-Z]{2}", country_code):
                web_search_tool["user_location"] = {
                    "type": "approximate",
                    "country": country_code,
                }

        return web_search_tool

    def _convert_prompt_messages_to_responses_input(
        self, prompt_messages: list[PromptMessage]
    ) -> list[dict]:
        input_messages = []
        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                if isinstance(message.content, str):
                    input_messages.append({"role": "developer", "content": message.content})
                else:
                    parts = self._convert_multimodal_content_to_responses_parts(message.content)
                    if parts:
                        input_messages.append({"role": "developer", "content": parts})
            elif isinstance(message, UserPromptMessage):
                if isinstance(message.content, str):
                    input_messages.append({"role": "user", "content": message.content})
                else:
                    parts = self._convert_multimodal_content_to_responses_parts(message.content)
                    if parts:
                        input_messages.append({"role": "user", "content": parts})
            elif isinstance(message, AssistantPromptMessage):
                if message.tool_calls:
                    for tc in message.tool_calls:
                        input_messages.append({
                            "type": "function_call",
                            "call_id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        })
                elif message.content:
                    input_messages.append({"role": "assistant", "content": message.content})
            elif isinstance(message, ToolPromptMessage):
                input_messages.append({
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                })
        return input_messages

    @staticmethod
    def _convert_multimodal_content_to_responses_parts(
        content_items: Optional[list],
    ) -> list[dict[str, Any]]:
        content_parts: list[dict[str, Any]] = []
        for content_item in content_items or []:
            if content_item.type == PromptMessageContentType.TEXT:
                content_parts.append({
                    "type": "input_text",
                    "text": content_item.data
                })
            elif content_item.type == PromptMessageContentType.IMAGE:
                image_c: ImagePromptMessageContent = content_item
                image_part = {"type": "input_image"}
                if image_c.url:
                    image_part["image_url"] = image_c.url
                else:
                    image_part["image_url"] = image_c.data
                if image_c.detail:
                    image_part["detail"] = image_c.detail.value
                content_parts.append(image_part)
            elif content_item.type == PromptMessageContentType.DOCUMENT:
                doc_c: DocumentPromptMessageContent = content_item
                file_part: dict[str, Any] = {"type": "input_file"}
                if doc_c.url:
                    file_part["file_url"] = doc_c.url
                elif doc_c.base64_data:
                    file_part["filename"] = doc_c.filename or "document"
                    file_part["file_data"] = (
                        f"data:{doc_c.mime_type};base64,{doc_c.base64_data}"
                    )
                if len(file_part) > 1:
                    content_parts.append(file_part)
        return content_parts

    def _chat_generate_with_responses(
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
        client = self._create_openai_client(credentials)
        endpoint_model = credentials.get("endpoint_model_name") or model

        input_messages = self._convert_prompt_messages_to_responses_input(prompt_messages)

        responses_params = {
            "model": endpoint_model,
            "input": input_messages,
        }

        if "temperature" in model_parameters:
            responses_params["temperature"] = model_parameters.get("temperature")
        if "top_p" in model_parameters:
            responses_params["top_p"] = model_parameters.get("top_p")
        if "max_tokens" in model_parameters:
            responses_params["max_output_tokens"] = model_parameters.pop("max_tokens")
        elif "max_completion_tokens" in model_parameters:
            responses_params["max_output_tokens"] = model_parameters.pop("max_completion_tokens")

        web_search_tool = self._extract_responses_web_search_config(model_parameters, credentials)
        response_tools = []

        if tools:
            for tool in tools:
                parameters = tool.parameters
                if isinstance(parameters, str):
                    try:
                        parameters = json.loads(parameters)
                    except json.JSONDecodeError:
                        parameters = {"type": "object", "properties": {}}
                elif not isinstance(parameters, dict):
                    parameters = {"type": "object", "properties": {}}

                tool_dict = {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                }
                response_tools.append(tool_dict)

        if web_search_tool:
            response_tools.append(web_search_tool)

        if response_tools:
            responses_params["tools"] = response_tools
            responses_params["tool_choice"] = "auto"

        if user and credentials.get("user_identity_support", "support") != "no_support":
            responses_params["safety_identifier"] = user

        if stop:
            responses_params["stop"] = stop

        response_format = model_parameters.get("response_format")
        if response_format:
            if response_format == "json_schema":
                json_schema_data = model_parameters.get("json_schema", {})
                if isinstance(json_schema_data, str):
                    try:
                        json_schema_data = json.loads(json_schema_data)
                    except json.JSONDecodeError:
                        json_schema_data = {}
                responses_params["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": json_schema_data.get("name", "response"),
                        "schema": json_schema_data.get("schema", {}),
                    }
                }
            else:
                responses_params["text"] = {
                    "format": {"type": response_format}
                }

        reasoning_effort = model_parameters.get("reasoning_effort")
        if reasoning_effort:
            responses_params["reasoning"] = {"effort": reasoning_effort}

        response = client.responses.create(
            **responses_params,
            stream=stream,
        )

        if stream:
            return self._handle_responses_stream_response(
                model, credentials, response, prompt_messages, tools
            )
        else:
            return self._handle_responses_response(
                model, credentials, response, prompt_messages, tools
            )

    def _handle_responses_response(
        self,
        model: str,
        credentials: dict,
        response: Any,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> LLMResult:
        content = ""
        if hasattr(response, "output") and response.output:
            for item in response.output:
                item_type = getattr(item, "type", "")
                if item_type == "reasoning":
                    summary_list = getattr(item, "summary", [])
                    summary_text = "\n".join(
                        s.text for s in summary_list if hasattr(s, "text") and s.text
                    )
                    if summary_text:
                        content += "<think>\n" + summary_text + "\n</think>"
                elif item_type == "message":
                    item_content = getattr(item, "content", None)
                    if isinstance(item_content, str):
                        if item_content:
                            content += item_content
                    elif isinstance(item_content, list):
                        for part in item_content:
                            part_type = getattr(part, "type", "")
                            if part_type in ("output_text", "text", "input_text"):
                                text_val = getattr(part, "text", "")
                                if text_val:
                                    content += text_val
                elif item_type in ("output_text", "text"):
                    text_val = getattr(item, "text", "")
                    if text_val:
                        content += text_val
        elif hasattr(response, "text") and response.text:
            content = response.text
        elif hasattr(response, "content") and response.content:
            content = response.content

        tool_calls = []
        if hasattr(response, "output") and response.output:
            for item in response.output:
                item_type = getattr(item, "type", "")
                if item_type == "function_call":
                    function_name = getattr(item, "name", "")
                    function_args = getattr(item, "arguments", "")
                    call_id = getattr(item, "call_id", "") or getattr(item, "id", "")

                    if isinstance(function_args, dict):
                        args_str = json.dumps(function_args)
                    elif isinstance(function_args, str):
                        args_str = function_args
                    else:
                        args_str = "{}"

                    tool_call = AssistantPromptMessage.ToolCall(
                        id=call_id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=function_name, arguments=args_str
                        ),
                    )
                    tool_calls.append(tool_call)

        assistant_prompt_message = AssistantPromptMessage(
            content=content, tool_calls=tool_calls
        )

        prompt_tokens = 0
        completion_tokens = 0
        if hasattr(response, "usage") and response.usage:
            usage_obj = response.usage
            prompt_tokens = getattr(usage_obj, "input_tokens", None) or getattr(usage_obj, "prompt_tokens", 0)
            completion_tokens = getattr(usage_obj, "output_tokens", None) or getattr(usage_obj, "completion_tokens", 0)
        else:
            prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
            completion_tokens = self._num_tokens_from_string(assistant_prompt_message.content or "")

        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        return LLMResult(
            model=model,
            message=assistant_prompt_message,
            usage=usage,
        )

    def _handle_responses_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Any,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> Generator:
        full_text = ""
        index = 0
        is_first = True
        is_reasoning = False

        pending_tool_calls = {}
        current_tool_call = None

        for chunk in response:
            if is_first:
                is_first = False

            chunk_type = getattr(chunk, "type", "")

            if chunk_type == "response.reasoning_summary_text.delta":
                delta_text = getattr(chunk, "delta", "")
                if delta_text:
                    if not is_reasoning:
                        delta_text = "<think>\n" + delta_text
                        is_reasoning = True
                    full_text += delta_text

                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_text, tool_calls=[]
                    )

                    yield LLMResultChunk(
                        model=model,
                        delta=LLMResultChunkDelta(
                            index=index, message=assistant_prompt_message
                        ),
                    )
                    index += 1

            elif chunk_type == "response.output_text.delta":
                delta_text = getattr(chunk, "delta", "")
                if delta_text:
                    if is_reasoning:
                        delta_text = "\n</think>" + delta_text
                        is_reasoning = False
                    full_text += delta_text

                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_text, tool_calls=[]
                    )

                    yield LLMResultChunk(
                        model=model,
                        delta=LLMResultChunkDelta(
                            index=index, message=assistant_prompt_message
                        ),
                    )
                    index += 1

            elif chunk_type == "response.output_item.added":
                item = getattr(chunk, "item", None)
                if item and hasattr(item, "type"):
                    item_type = getattr(item, "type", "")

                    if item_type == "function_call":
                        function_name = getattr(item, "name", "")
                        call_id = getattr(item, "call_id", "")

                        if function_name and call_id:
                            pending_tool_calls[call_id] = {
                                "id": call_id,
                                "name": function_name,
                                "arguments": "",
                            }
                            current_tool_call = call_id

            elif chunk_type == "response.function_call_arguments.delta":
                delta_args = getattr(chunk, "delta", "")
                if current_tool_call and current_tool_call in pending_tool_calls:
                    pending_tool_calls[current_tool_call]["arguments"] += delta_args

            elif chunk_type == "response.function_call_arguments.done":
                call_id = getattr(chunk, "item_id", "")
                final_args = getattr(chunk, "arguments", "")
                if call_id and call_id in pending_tool_calls:
                    pending_tool_calls[call_id]["arguments"] = final_args

            elif chunk_type == "response.output_item.done":
                item = getattr(chunk, "item", None)
                if item and hasattr(item, "type"):
                    item_type = getattr(item, "type", "")

                    if item_type == "function_call":
                        function_name = getattr(item, "name", "")
                        function_args = getattr(item, "arguments", "")
                        call_id = getattr(item, "call_id", "")

                        if call_id in pending_tool_calls:
                            final_args = pending_tool_calls[call_id]["arguments"] or function_args
                        else:
                            final_args = function_args

                        if function_name:
                            tool_call = AssistantPromptMessage.ToolCall(
                                id=call_id,
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=function_name,
                                    arguments=final_args or "{}",
                                ),
                            )

                            assistant_prompt_message = AssistantPromptMessage(
                                content="", tool_calls=[tool_call]
                            )

                            yield LLMResultChunk(
                                model=model,
                                delta=LLMResultChunkDelta(
                                    index=index, message=assistant_prompt_message
                                ),
                            )
                            index += 1

                            if call_id in pending_tool_calls:
                                del pending_tool_calls[call_id]
                            if call_id == current_tool_call:
                                current_tool_call = None

            elif hasattr(chunk, "delta") and hasattr(chunk.delta, "text"):
                delta_text = chunk.delta.text or ""
                if delta_text:
                    full_text += delta_text
                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_text, tool_calls=[]
                    )
                    yield LLMResultChunk(
                        model=model,
                        delta=LLMResultChunkDelta(
                            index=index, message=assistant_prompt_message
                        ),
                    )
                    index += 1

        prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
        full_assistant_prompt_message = AssistantPromptMessage(content=full_text)
        completion_tokens = self._num_tokens_from_string(full_assistant_prompt_message.content or "")
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        yield LLMResultChunk(
            model=model,
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=""),
                finish_reason="stop",
                usage=usage,
            ),
        )
