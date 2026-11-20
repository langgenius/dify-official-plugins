import json
import re
from collections.abc import Generator
from hashlib import sha256

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    DeveloperPromptMessage,
    PromptMessageFunction,
    SystemPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeServerUnavailableError

from models.llm import _qwen_long, _sse, _wire

COMMON_FIELDS = {
    "max_tokens",
    "temperature",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "response_format",
    "json_schema",
    "tool_choice",
    "reasoning_effort",
    "stop_sequences",
}
TONGYI_FIELDS = COMMON_FIELDS | {
    "enable_search",
    "search_options",
    "enable_thinking",
    "thinking_budget",
    "top_k",
    "repetition_penalty",
    "max_completion_tokens",
    "incremental_output",
    "translation_options",
    "source_lang",
    "target_lang",
    "domains",
    "parallel_tool_calls",
}
XAI_FIELDS = COMMON_FIELDS | {
    "service_tier",
    "search_parameters",
    "max_completion_tokens",
    "parallel_tool_calls",
    "presencePenalty",
    "frequencyPenalty",
    "stopSequences",
}
AUDIO_FIELDS = COMMON_FIELDS | {
    "enable_stream",
    "max_completion_tokens",
    "modalities",
    "audio",
    "parallel_tool_calls",
}
THINKING_DEFAULTS = (
    "qwen-plus-latest",
    "qwen-plus-2025-04-28",
    "qwen-turbo-latest",
    "qwen-turbo-2025-04-28",
    "qwen-flash",
    "qwen3-max-2026-01-23",
    "qwen3-max-preview",
    "qwen3-vl-plus",
    "qwen3-vl-flash",
    "qwen3-omni-flash",
    "qwen3.5-",
    "qwen3.6-",
    "qwen3.7-",
    "qwen3.8-",
)
DEEPSEEK_EFFORTS = {
    "deepseek-v4.1-flash": ("low", "high", "max"),
    "deepseek-v4.1-flash-1017": ("low", "high", "max"),
    "deepseek-v4-pro": ("high", "max"),
    "deepseek-v4-flash-0731": ("low", "high", "max"),
}


def normalize_deepseek_parameters(model, parameters):
    if model not in DEEPSEEK_EFFORTS:
        return
    parameters.setdefault("enable_thinking", True)
    if parameters["enable_thinking"] is False or parameters.get("reasoning_effort") in (None, ""):
        parameters.pop("reasoning_effort", None)
    elif parameters["reasoning_effort"] not in DEEPSEEK_EFFORTS[model]:
        raise InvokeBadRequestError(f"Invalid reasoning_effort for {model}")


def _tongyi(model, messages, params, output_format, tools, stream):
    if model.startswith("qwen-mt"):
        translation = {}
        if (provided := params.pop("translation_options", None)) is not None:
            translation = _wire.json_object(provided, "translation_options")
        for name in ("source_lang", "target_lang", "domains"):
            if (value := params.pop(name, None)) is not None:
                translation[name] = value
        translation.setdefault("domains", None)
        params["translation_options"] = {
            key: translation[key]
            for key in ("source_lang", "target_lang", "domains")
            if key in translation
        }
        if not messages or messages[-1].role.value != "user":
            raise InvokeBadRequestError("Qwen translation requires a final user message")
        return messages[-1:], output_format, False
    if model.startswith(THINKING_DEFAULTS):
        params.setdefault("enable_thinking", model == "qwen3.8-max")
    if model in {
        "glm-5.1",
        "glm-5",
        "glm-4.7",
        "glm-4.6",
        "glm-4.5",
        "glm-4.5-air",
        "deepseek-v3.2",
        "deepseek-v3.2-exp",
        "deepseek-v3.1",
    }:
        params.setdefault("enable_thinking", False)
    normalize_deepseek_parameters(model, params)
    if model == "qwen3.8-max":
        params["preserve_thinking"] = False
        if not params["enable_thinking"]:
            params.pop("reasoning_effort", None)
        elif (temp := params.get("temperature")) is not None and temp < 0.6:
            params["temperature"] = 0.6
        messages = [
            message.model_copy(
                update={
                    "content": re.sub(
                        r"<think>\n(?:(?!</?think>).)*\n</think>",
                        "",
                        message.content,
                        flags=re.DOTALL,
                    )
                }
            )
            if isinstance(message, AssistantPromptMessage) and isinstance(message.content, str)
            else message
            for message in messages
        ]
    if output_format and output_format["type"] == "json_schema":
        output_format["json_schema"].setdefault("strict", True)
        if any(
            item.type.value in {"image", "audio", "video"}
            for message in messages
            if isinstance(message.content, list)
            for item in message.content
        ):
            directive = "Return a JSON object matching this JSON Schema:\n" + json.dumps(
                output_format["json_schema"]["schema"],
                ensure_ascii=False,
            )
            output_format = {"type": "json_object"}
            if (
                messages
                and isinstance(messages[0], SystemPromptMessage)
                and isinstance(messages[0].content, str)
            ):
                messages = [
                    messages[0].model_copy(
                        update={
                            "content": messages[0].content + "\n\n" + directive,
                        }
                    ),
                    *messages[1:],
                ]
            else:
                messages = [SystemPromptMessage(content=directive), *messages]
    requires_stream = (
        (
            model.startswith(THINKING_DEFAULTS)
            and model not in {"qwen3.6-flash", "qwen3.6-flash-2026-04-16"}
            and params.get("enable_thinking")
        )
        or (
            model
            in {
                "glm-5",
                "glm-4.7",
                "glm-4.6",
                "glm-4.5",
                "glm-4.5-air",
                "kimi-k2.5",
                "kimi-k2-thinking",
                *DEEPSEEK_EFFORTS,
            }
            and params.get("enable_thinking")
        )
        or model.startswith(("qwq-", "qvq-"))
        or model.startswith("qwen3-")
        and not model.startswith(("qwen3-coder", "qwen3-max", "qwen3-vl-plus", "qwen3-vl-flash"))
    )
    if requires_stream:
        stream = True
        params["incremental_output"] = True
    if "max_completion_tokens" in params:
        params.pop("max_tokens", None)
    if stream:
        params.setdefault("incremental_output", not tools)
    return messages, output_format, stream


def _chat_message(llm, model, message):
    if isinstance(message, DeveloperPromptMessage):
        return {"role": "developer", "content": message.get_text_content()}
    credentials = {"function_calling_type": "tool_call"}
    converted = llm._convert_prompt_message_to_dict(message, credentials)
    if message.role.value != "user" or not isinstance(message.content, list):
        return converted
    if not model.startswith(("gpt-audio", "qwen", "qwq", "qvq")):
        return converted
    parts = []
    for item in message.content:
        if isinstance(item, AudioPromptMessageContent):
            if model.startswith("gpt-audio"):
                kind = item.format.lower().lstrip(".")
                if not item.base64_data or kind not in {"wav", "mp3"}:
                    raise InvokeBadRequestError("OpenAI audio input requires base64 WAV or MP3")
                parts.append(
                    {
                        "type": "input_audio",
                        "input_audio": {"data": item.base64_data, "format": kind},
                    }
                )
            else:
                parts.append({"type": "audio_url", "audio_url": {"url": item.data}})
        else:
            single = message.model_copy(update={"content": [item]})
            value = llm._convert_prompt_message_to_dict(single, credentials)["content"]
            if not value:
                raise InvokeBadRequestError(f"Unsupported Chat content: {item.type.value}")
            parts.extend(value)
    return {**converted, "content": parts}


def invoke(
    llm, family, model, credentials, messages, parameters, tools, stop, stream, user
) -> Generator:
    allowed = {"tongyi": TONGYI_FIELDS, "xai": XAI_FIELDS, "audio": AUDIO_FIELDS}[family]
    params = {key: value for key, value in parameters.items() if key in allowed}
    stream = stream and params.pop("enable_stream", True) is not False
    stop = stop or params.pop("stop_sequences", None) or params.pop("stopSequences", None)
    params.pop("stop_sequences", None)
    params.pop("stopSequences", None)
    for name in ("audio", "search_options", "tool_choice"):
        if isinstance(params.get(name), dict):
            _wire.reject_controls(params[name])
    output_format = _wire.structured_format(params)
    if family == "xai":
        if (search := params.get("search_parameters")) is not None:
            params["search_parameters"] = _wire.json_object(search, "search_parameters")
            _wire.reject_controls(params["search_parameters"])
        if "-non-reasoning" not in model and (
            model.startswith(("grok-3-mini", "grok-4", "grok-code", "grok-build"))
            or model.endswith("-reasoning")
        ):
            stop = None
            for key in (
                "presence_penalty",
                "frequency_penalty",
                "presencePenalty",
                "frequencyPenalty",
            ):
                params.pop(key, None)
    elif family == "tongyi":
        messages, output_format, stream = _tongyi(
            model, messages, params, output_format, tools, stream
        )
    elif model == "gpt-audio-mini-2025-12-15":
        stream = False

    payload = {
        **params,
        "model": model,
        "stream": stream,
        "messages": _qwen_long.convert(messages, tools)
        if model == "qwen-long"
        else [_chat_message(llm, model, message) for message in messages],
    }
    if output_format and output_format["type"] != "text":
        payload["response_format"] = output_format
    if stop:
        payload["stop"] = stop
    if tools:
        payload["tools"] = [PromptMessageFunction(function=tool).model_dump() for tool in tools]
        payload.setdefault("tool_choice", "auto")
    else:
        payload.pop("tool_choice", None)
    if user and family == "audio":
        digest = sha256(user.encode()).hexdigest()
        payload.update(safety_identifier=digest, prompt_cache_key=digest)
    if stream:
        payload["stream_options"] = {"include_usage": True}
    request_options = {}
    if model == "qwen-long" and any(
        isinstance(message["content"], list) for message in payload["messages"]
    ):
        request_options["timeout"] = (10, _qwen_long.REQUEST_TIMEOUT_SECONDS)
    with llm._request(
        "chat/completions", credentials, json=payload, stream=stream, **request_options
    ) as response:
        if stream:
            resolved = {**credentials, "mode": "chat", "function_calling_type": "tool_call"}
            yield from llm._handle_generate_stream_response(
                model,
                resolved,
                _sse.ChatCompletionSSEStreamResponse(response),
                messages,
            )
            return
        result = response.json()
        if not isinstance(result, dict) or not result.get("choices"):
            if isinstance(result, dict) and result.get("error"):
                _wire.response_error(result["error"])
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid Chat response")
        choice = result["choices"][0]
        message = choice.get("message") or {}
        content = _wire.thinking_text(
            message.get("reasoning_content") or message.get("reasoning") or ""
        ) + (message.get("content") or message.get("refusal") or "")
        calls = [
            _wire.tool_call(item["id"], item["function"]["name"], item["function"]["arguments"])
            for item in message.get("tool_calls") or []
            if choice.get("finish_reason") != "length"
        ]
        usage = result.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is None or completion_tokens is None:
            from models.llm import _openai_responses

            if prompt_tokens is None:
                prompt_tokens = _openai_responses.count_messages(model, messages, tools)
            if completion_tokens is None:
                completion_tokens = _openai_responses.count_text(model, content)
        yield _wire.chunk(
            result.get("model", model),
            content,
            calls=calls,
            finish=choice.get("finish_reason"),
            usage=llm._calc_response_usage(model, credentials, prompt_tokens, completion_tokens),
        )
