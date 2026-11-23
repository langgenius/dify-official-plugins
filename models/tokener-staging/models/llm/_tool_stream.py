import json

import requests
from dify_plugin.entities.model.message import AssistantPromptMessage


def _has_complete_arguments(arguments: str) -> bool:
    try:
        json.loads(arguments)
    except ValueError:
        return False
    return True


class _ToolCallStreamResponse(requests.Response):
    def __init__(self, response: requests.Response) -> None:
        super().__init__()
        self.response = response
        self.tool_calls: list[AssistantPromptMessage.ToolCall] = []
        self.indexed_calls: dict[int, AssistantPromptMessage.ToolCall] = {}

    def iter_lines(self, chunk_size=512, decode_unicode=False, delimiter=None):
        for line in self.response.iter_lines(
            chunk_size=chunk_size, decode_unicode=decode_unicode, delimiter=delimiter
        ):
            decoded = line.strip().removeprefix("data:").lstrip()
            try:
                payload = json.loads(decoded)
            except (ValueError, TypeError):
                yield line
                continue
            if not isinstance(payload, dict) or not payload.get("choices"):
                yield line
                continue
            delta = payload["choices"][0].get("delta", {})
            fragments = delta.get("tool_calls")
            if not fragments:
                yield line
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
            yield f"data: {json.dumps(payload)}"
