import re


def provider_features(model_id: str, capabilities: set[str]) -> set[str]:
    features = set()
    if model_id.startswith("gpt-audio"):
        features.add("audio")
    if "vision" in capabilities and model_id.startswith(
        ("gpt-4", "gpt-5", "gpt-6", "claude-", "gemini-")
    ):
        features.add("document")
    if "vision" in capabilities and "-image" not in model_id and model_id.startswith("gemini-"):
        features.update(("audio", "video"))
    if "vision" in capabilities and model_id.startswith(("qwen3", "qwen-vl", "qvq-")):
        features.add("video")
    if model_id == "qwen-long":
        features.add("document")
    return features


def provider_rules(model_id: str, features: list[str]) -> dict[str, str | tuple[str, ...]]:
    if model_id.startswith(("gpt-", "o1", "o3", "o4")):
        rules = {"enable_stream": "boolean"}
        if model_id.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")):
            rules["reasoning_summary"] = ("auto",)
            rules["service_tier"] = ("auto", "default", "flex", "priority")
        if model_id.startswith(("gpt-5", "gpt-6")):
            rules["verbosity"] = ("low", "medium", "high")
        if model_id.startswith("gpt-6"):
            rules.update(
                reasoning_mode=("standard", "pro"),
                reasoning_context=("auto", "current_turn", "all_turns"),
            )
        return rules
    if model_id.startswith("claude-"):
        rules = {
            f"prompt_caching_{name}": "boolean"
            for name in (
                "tool_definitions",
                "system_message",
                "images",
                "documents",
                "tool_results",
            )
        }
        rules.update(prompt_caching_ttl=("5m", "1h"), prompt_caching_message_flow="int")
        if "agent-thought" in features:
            rules.update(thinking="boolean", thinking_display=("summarized", "omitted"))
            if model_id.startswith(("claude-opus-4-7", "claude-opus-4-8")):
                rules["effort"] = ("low", "medium", "high", "max")
            elif re.match(r"claude-(?:opus|sonnet|haiku|fable|mythos)-5(?:-|$)", model_id):
                rules["effort"] = ("low", "medium", "high", "xhigh", "max")
            else:
                rules["thinking_budget"] = "int"
        return rules
    if model_id.startswith("gemini-"):
        rules = {"use_inline_file": "boolean"} if "document" in features else {}
        if model_id.startswith(("gemini-3", "gemini-4")):
            rules["media_resolution"] = ("Default", "Low", "Medium", "High")
        if (
            model_id.startswith(
                ("gemini-3.1", "gemini-3.5", "gemini-3.6", "gemini-3.7", "gemini-3.8")
            )
            or model_id == "gemini-4-argon"
        ):
            rules["service_tier"] = ("flex", "standard", "priority")
        if "-image" in model_id:
            rules["aspect_ratio"] = "string"
            if model_id.startswith("gemini-3"):
                rules["resolution"] = ("1K", "2K", "4K")
            return rules
        rules.update(grounding="boolean", url_context="boolean", code_execution="boolean")
        if "agent-thought" in features:
            rules["include_thoughts"] = "boolean"
            if model_id.startswith(("gemini-3", "gemini-4")):
                rules["thinking_level"] = ("Minimal", "Low", "Medium", "High")
            else:
                rules.update(thinking_mode="boolean", thinking_budget="int")
        return rules
    if model_id.startswith("qwen-mt-"):
        return dict.fromkeys(("source_lang", "target_lang", "domains"), "string")
    if model_id.startswith("qwen") and model_id != "qwen-long":
        rules = {"enable_search": "boolean"}
        if "agent-thought" in features:
            rules["enable_thinking"] = "boolean"
            if model_id == "qwen3.8-max":
                rules["reasoning_effort"] = ("low", "medium", "xhigh")
            else:
                rules["thinking_budget"] = "int"
        return rules
    if model_id.startswith("grok-"):
        rules = {"search_parameters": "text"}
        if model_id.startswith("grok-3-mini"):
            rules["reasoning_effort"] = ("low", "high")
        elif model_id.startswith("grok-4.5"):
            rules["reasoning_effort"] = ("low", "medium", "high")
        return rules
    return {}
