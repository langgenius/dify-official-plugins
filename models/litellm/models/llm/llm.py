import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeError


class LiteLLMLargeLanguageModel(OAICompatLargeLanguageModel):
    """Chat and completion models served by a LiteLLM Proxy.

    Normalize missing content in tool responses to an empty string.
    """

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> LLMResult:
        response_json: dict = response.json()

        choices = response_json.get("choices")
        if not choices:
            raise InvokeError("LiteLLM Proxy returned a response without choices")
        output = choices[0]

        completion_type = LLMMode.value_of(credentials["mode"])
        function_calling_type = credentials.get("function_calling_type", "no_call")

        content = ""
        tool_calls = None
        if completion_type is LLMMode.CHAT:
            message = output.get("message") or {}
            content = message.get("content")
            if function_calling_type == "tool_call":
                tool_calls = message.get("tool_calls")
            elif function_calling_type == "function_call":
                tool_calls = message.get("function_call")
        else:
            content = output.get("text")
        if not isinstance(content, str):
            content = ""

        assistant_message = AssistantPromptMessage(content=content, tool_calls=[])
        if tool_calls:
            if function_calling_type == "tool_call":
                assistant_message.tool_calls = self._extract_response_tool_calls(tool_calls)
            else:
                function_call = self._extract_response_function_call(tool_calls)
                assistant_message.tool_calls = [function_call] if function_call else []

        return LLMResult(
            id=response_json.get("id"),
            model=response_json.get("model", model),
            message=assistant_message,
            usage=self._get_response_usage(
                model,
                credentials,
                prompt_messages,
                assistant_message,
                response_json.get("usage"),
                tools,
            ),
        )
