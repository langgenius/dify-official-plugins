"""Preserve Kimi K3.1 reasoning when tool results are sent back to the model."""

import re

from dify_plugin.entities.model.message import AssistantPromptMessage


class KimiK31ReasoningMixin:
    _KIMI_K31_MODELS = {"kimi-k3.1-pro", "kimi-k3.1-pro-highspeed"}
    _KIMI_THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)

    def _convert_prompt_message_to_dict(self, message, credentials=None):
        payload = super()._convert_prompt_message_to_dict(message, credentials)
        if not (credentials or {}).get("_kimi_k31") or not isinstance(message, AssistantPromptMessage):
            return payload

        content = message.content or ""
        reasoning = None
        if isinstance(message.opaque_body, dict):
            reasoning = message.opaque_body.get("reasoning_content")
        if isinstance(content, str):
            matches = self._KIMI_THINK_PATTERN.findall(content)
            if not isinstance(reasoning, str) and matches:
                reasoning = "\n\n".join(matches)
            content = self._KIMI_THINK_PATTERN.sub("", content)
        payload["content"] = content
        payload["reasoning_content"] = reasoning if isinstance(reasoning, str) else ""
        return payload

    def _handle_generate_response(self, model, credentials, response, prompt_messages):
        result = super()._handle_generate_response(model, credentials, response, prompt_messages)
        if model not in self._KIMI_K31_MODELS:
            return result
        reasoning = response.json()["choices"][0].get("message", {}).get("reasoning_content")
        if isinstance(reasoning, str):
            opaque = result.message.opaque_body if isinstance(result.message.opaque_body, dict) else {}
            result.message.opaque_body = {**opaque, "reasoning_content": reasoning}
            if reasoning:
                result.message.content = f"<think>{reasoning}</think>{result.message.content or ''}"
        return result
