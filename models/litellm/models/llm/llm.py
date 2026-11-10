import requests
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import AssistantPromptMessage, PromptMessage
from dify_plugin.errors.model import InvokeError


class LiteLLMLargeLanguageModel(OAICompatLargeLanguageModel):
    """Chat and completion models served by a LiteLLM Proxy.

    When a model answers with tool calls only, the proxy can leave out
    `message.content` or set it to `null`. The shared base class reads
    `message["content"]` and fails with `KeyError`, so this class handles
    non-streaming responses itself and treats a missing value as an empty string.
    """

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: requests.Response,
        prompt_messages: list[PromptMessage],
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

        usage = response_json.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = self._num_tokens_from_messages(prompt_messages, credentials=credentials)
        completion_tokens = usage.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = self._num_tokens_from_string(content)

        return LLMResult(
            id=response_json.get("id"),
            model=response_json.get("model", model),
            message=assistant_message,
            usage=self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens),
        )
