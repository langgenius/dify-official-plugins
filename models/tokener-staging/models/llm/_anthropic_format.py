import re
from decimal import Decimal

from dify_plugin.entities.model.message import AssistantPromptMessage, SystemPromptMessage

FAST_MODELS = {
    "claude-fable-5-2",
    "claude-mythos-5-2",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
}


def _cache_writes(usage):
    creation = usage.get("cache_creation") or {}
    short = creation.get("ephemeral_5m_input_tokens") or 0
    long = creation.get("ephemeral_1h_input_tokens") or 0
    total = usage.get("cache_creation_input_tokens")
    if total is None:
        return short, long, short + long
    if total != short + long:
        return 0, 0, total
    return short, long, total


def prompt_tokens(model, usage, parameters):
    short, long, total = _cache_writes(usage)
    writes = (
        short * 5 // 4 + long * 2
        if short or long
        else total * (8 if parameters.get("prompt_caching_ttl") == "1h" else 5) // 4
    )
    divisor = (
        40
        if model
        in {
            "claude-fable-5-1",
            "claude-fable-5-2",
            "claude-mythos-5-1",
            "claude-mythos-5-2",
        }
        else (20 if model in {"claude-opus-5-5", "claude-sonnet-5-5"} else 10)
    )
    return (
        (usage.get("input_tokens") or 0)
        + writes
        + (usage.get("cache_read_input_tokens") or 0) // divisor
    )


def _raw_input_tokens(usage):
    return (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + _cache_writes(usage)[2]
    )


def priced_usage(
    llm,
    model,
    credentials,
    usage,
    parameters,
    *,
    reason=None,
    stop_details=None,
    has_content: bool = True,
):
    result = llm._calc_response_usage(
        model,
        credentials,
        prompt_tokens(model, usage, parameters),
        usage.get("output_tokens") or 0,
    )
    category = stop_details.get("category") if isinstance(stop_details, dict) else None
    unbilled = (
        reason == "refusal"
        and not has_content
        and category not in {"bio", "frontier_llm", "reasoning_extraction"}
    )
    multiplier = Decimal(0 if unbilled else 1)
    if model in FAST_MODELS and (usage.get("speed") or parameters.get("speed")) == "fast":
        multiplier *= 2
    if usage.get("inference_geo") == "us":
        version = re.match(r"^claude-[a-z]+-(\d+)(?:-(\d{1,2}))?(?:-|$)", model)
        if version and (int(version[1]), int(version[2] or 0)) >= (4, 6):
            multiplier *= Decimal("1.1")
    if model == "claude-haiku-5-5" and _raw_input_tokens(usage) > 100_000:
        multiplier *= 5
    if multiplier != 1:
        for name in (
            "prompt_unit_price",
            "prompt_price",
            "completion_unit_price",
            "completion_price",
        ):
            setattr(result, name, getattr(result, name) * multiplier)
        result.total_price = result.prompt_price + result.completion_price
    return result


def code_block_mode(
    owner,
    model,
    credentials,
    prompt_messages,
    model_parameters,
    tools,
    stop,
    stream,
    user,
    no_prefill,
):
    mode = model_parameters.pop("response_format", None)
    schema = model_parameters.get("json_schema")
    has_schema = schema is not None and (not isinstance(schema, str) or bool(schema.strip()))
    if mode and not (mode == "JSON" and has_schema):
        template = (
            "You should always follow the instructions and output a valid "
            f"{mode} object.\nThe structure of the {mode} object you can found in the "
            'instructions, use {"answer": "$your_answer"} as the default structure\n'
            "if you are not sure about the structure.\n\n<instructions>\n"
        )
        if prompt_messages and isinstance(prompt_messages[0], SystemPromptMessage):
            instructions = str(prompt_messages[0].content)
            prompt_messages[0] = SystemPromptMessage(
                content=template + instructions + "\n</instructions>\n"
            )
        else:
            prompt_messages.insert(
                0,
                SystemPromptMessage(
                    content=template + f"Please output a valid {mode} object.\n</instructions>\n"
                ),
            )
        if not no_prefill:
            prompt_messages.append(AssistantPromptMessage(content=f"\n```{mode}"))
        stop = list(stop or [])
        for marker in ("```\n", "\n```"):
            if marker not in stop:
                stop.append(marker)
        model_parameters.pop("json_schema", None)
    return owner._invoke(
        model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    )
