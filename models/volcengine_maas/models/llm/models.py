from decimal import Decimal
from typing import Optional

from dify_plugin.entities.model import (
    ModelFeature,
    PriceConfig,
)
from dify_plugin.entities.model.llm import LLMMode
from pydantic import BaseModel
from volcenginesdkarkruntime.types.chat.completion_create_params import Thinking


class ModelProperties(BaseModel):
    context_size: int
    max_tokens: int
    mode: LLMMode


class ModelConfig(BaseModel):
    properties: ModelProperties
    features: list[ModelFeature]
    pricing: Optional[PriceConfig] = None


configs: dict[str, ModelConfig] = {
    "Doubao-Seed-1.6-vision": ModelConfig(
        properties=ModelProperties(context_size=262144, max_tokens=32768, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION, ModelFeature.VIDEO,
                  ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL, ModelFeature.STRUCTURED_OUTPUT],
        pricing=PriceConfig(input=Decimal("0.0008"), output=Decimal("0.0080"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "DeepSeek-V3.1": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=32768, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0040"), output=Decimal("0.0120"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Kimi-K2": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=32768, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0040"), output=Decimal("0.0160"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-Seed-1.6": ModelConfig(
        properties=ModelProperties(context_size=262144, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION, ModelFeature.VIDEO,
                  ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL, ModelFeature.STRUCTURED_OUTPUT],
        pricing=PriceConfig(input=Decimal("0.0024"), output=Decimal("0.0240"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-Seed-1.6-flash": ModelConfig(
        properties=ModelProperties(context_size=262144, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION, ModelFeature.VIDEO,
                  ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL, ModelFeature.STRUCTURED_OUTPUT],
        pricing=PriceConfig(input=Decimal("0.0006"), output=Decimal("0.0060"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-Seed-1.6-thinking": ModelConfig(
        properties=ModelProperties(context_size=262144, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION, ModelFeature.VIDEO,
                  ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0024"), output=Decimal("0.0240"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-thinking-vision-pro": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION, ModelFeature.VIDEO],
        pricing=PriceConfig(input=Decimal("0.0030"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-UI-TARS": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION],
        pricing=PriceConfig(input=Decimal("0.0035"), output=Decimal("0.0120"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-vision-lite": ModelConfig(
        properties=ModelProperties(context_size=65536, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION],
        pricing=PriceConfig(input=Decimal("0.0015"), output=Decimal("0.0045"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-vision-pro": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION, ModelFeature.VIDEO],
        pricing=PriceConfig(input=Decimal("0.0030"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-thinking-pro": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0040"), output=Decimal("0.0160"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-thinking-pro-m": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION,
                  ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
    ),
    "DeepSeek-R1-Distill-Qwen-32B": ModelConfig(
        properties=ModelProperties(context_size=65536, max_tokens=8192, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
        pricing=PriceConfig(input=Decimal("0.0015"), output=Decimal("0.0060"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "DeepSeek-R1-Distill-Qwen-7B": ModelConfig(
        properties=ModelProperties(context_size=65536, max_tokens=8192, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
        pricing=PriceConfig(input=Decimal("0.0006"), output=Decimal("0.0024"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "DeepSeek-R1": ModelConfig(
        properties=ModelProperties(context_size=65536, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0040"), output=Decimal("0.0160"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "DeepSeek-V3": ModelConfig(
        properties=ModelProperties(context_size=128000, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0020"), output=Decimal("0.0080"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-vision-pro-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=12288, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION],
        pricing=PriceConfig(input=Decimal("0.0030"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-pro-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=12288, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0008"), output=Decimal("0.0020"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-lite-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=12288, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0003"), output=Decimal("0.0006"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-1.5-pro-256k": ModelConfig(
        properties=ModelProperties(context_size=262144, max_tokens=12288, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
        pricing=PriceConfig(input=Decimal("0.0050"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-vision-pro-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION],
        pricing=PriceConfig(input=Decimal("0.0030"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-vision-lite-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.VISION],
        pricing=PriceConfig(input=Decimal("0.0015"), output=Decimal("0.0045"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-pro-4k": ModelConfig(
        properties=ModelProperties(context_size=4096, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0008"), output=Decimal("0.0020"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-lite-4k": ModelConfig(
        properties=ModelProperties(context_size=4096, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0003"), output=Decimal("0.0006"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-pro-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL, ModelFeature.STREAM_TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0008"), output=Decimal("0.0020"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-lite-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0003"), output=Decimal("0.0006"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-pro-256k": ModelConfig(
        properties=ModelProperties(context_size=262144, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
        pricing=PriceConfig(input=Decimal("0.0050"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-pro-128k": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0050"), output=Decimal("0.0090"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Doubao-lite-128k": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
        pricing=PriceConfig(input=Decimal("0.0008"), output=Decimal("0.0010"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Skylark2-pro-4k": ModelConfig(
        properties=ModelProperties(context_size=4096, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
    ),
    "Llama3-8B": ModelConfig(
        properties=ModelProperties(context_size=8192, max_tokens=8192, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
    ),
    "Llama3-70B": ModelConfig(
        properties=ModelProperties(context_size=8192, max_tokens=8192, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
    ),
    "Moonshot-v1-8k": ModelConfig(
        properties=ModelProperties(context_size=8192, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0120"), output=Decimal("0.0120"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Moonshot-v1-32k": ModelConfig(
        properties=ModelProperties(context_size=32768, max_tokens=16384, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0240"), output=Decimal("0.0240"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "Moonshot-v1-128k": ModelConfig(
        properties=ModelProperties(context_size=131072, max_tokens=65536, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
        pricing=PriceConfig(input=Decimal("0.0600"), output=Decimal("0.0600"), unit=Decimal("0.001"), currency="RMB"),
    ),
    "GLM3-130B": ModelConfig(
        properties=ModelProperties(context_size=8192, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
    ),
    "GLM3-130B-Fin": ModelConfig(
        properties=ModelProperties(context_size=8192, max_tokens=4096, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT, ModelFeature.TOOL_CALL],
    ),
    "Mistral-7B": ModelConfig(
        properties=ModelProperties(context_size=8192, max_tokens=2048, mode=LLMMode.CHAT),
        features=[ModelFeature.AGENT_THOUGHT],
    ),
}


def get_model_config(credentials: dict) -> ModelConfig:
    base_model = credentials.get("base_model_name", "")
    model_configs = configs.get(base_model)
    if not model_configs:
        return ModelConfig(
            properties=ModelProperties(
                context_size=int(credentials.get("context_size", 0)),
                max_tokens=int(credentials.get("max_tokens", 0)),
                mode=LLMMode.value_of(credentials.get("mode", "chat")),
            ),
            features=[],
        )
    return model_configs


def get_v2_req_params(credentials: dict, model_parameters: dict, stop: list[str] | None = None):
    req_params = {}
    model_configs = get_model_config(credentials)
    if model_configs:
        req_params["max_prompt_tokens"] = model_configs.properties.context_size
        req_params["max_new_tokens"] = model_configs.properties.max_tokens
    if model_parameters.get("max_tokens"):
        req_params["max_new_tokens"] = model_parameters.get("max_tokens")
    if model_parameters.get("temperature"):
        req_params["temperature"] = model_parameters.get("temperature")
    if model_parameters.get("top_p"):
        req_params["top_p"] = model_parameters.get("top_p")
    if model_parameters.get("top_k"):
        req_params["top_k"] = model_parameters.get("top_k")
    if model_parameters.get("presence_penalty"):
        req_params["presence_penalty"] = model_parameters.get("presence_penalty")
    if model_parameters.get("frequency_penalty"):
        req_params["frequency_penalty"] = model_parameters.get("frequency_penalty")
    if stop:
        req_params["stop"] = stop
    if model_parameters.get("skip_moderation"):
        req_params["skip_moderation"] = model_parameters.get("skip_moderation")
    if model_parameters.get("thinking"):
        thinking: Thinking = {"type": model_parameters["thinking"]}
        req_params["thinking"] = thinking
    return req_params


def get_v3_req_params(credentials: dict, model_parameters: dict, stop: list[str] | None = None):
    req_params = {}
    model_configs = get_model_config(credentials)
    if model_configs:
        req_params["max_tokens"] = model_configs.properties.max_tokens
    if model_parameters.get("max_tokens"):
        req_params["max_tokens"] = model_parameters.get("max_tokens")
    if model_parameters.get("temperature"):
        req_params["temperature"] = model_parameters.get("temperature")
    if model_parameters.get("top_p"):
        req_params["top_p"] = model_parameters.get("top_p")
    if model_parameters.get("presence_penalty"):
        req_params["presence_penalty"] = model_parameters.get("presence_penalty")
    if model_parameters.get("frequency_penalty"):
        req_params["frequency_penalty"] = model_parameters.get("frequency_penalty")
    if stop:
        req_params["stop"] = stop
    if model_parameters.get("skip_moderation"):
        req_params["skip_moderation"] = model_parameters.get("skip_moderation")
    if model_parameters.get("thinking"):
        thinking: Thinking = {"type": model_parameters["thinking"]}
        req_params["thinking"] = thinking
    if model_parameters.get("response_format"):
        req_params["response_format"] = model_parameters.get("response_format")
    return req_params
