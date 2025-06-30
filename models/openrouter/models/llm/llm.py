from collections.abc import Generator
from typing import Optional, Union
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin import OAICompatLargeLanguageModel


class OpenRouterLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = "https://openrouter.ai/api/v1"
        credentials["mode"] = self.get_model_mode(model).value
        credentials["function_calling_type"] = "tools"  # change to "tools"

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
        self._update_credential(model, credentials)
        reasoning_budget = model_parameters.get('reasoning_budget')
        if reasoning_budget:
            model_parameters.pop('reasoning_budget')
            model_parameters['reasoning'] = {'max_tokens': reasoning_budget}
        reasoning_effort = model_parameters.get('reasoning_effort')
        if reasoning_effort:
            model_parameters.pop('reasoning_effort')
            model_parameters['reasoning'] = {'effort': reasoning_effort}
        # Add parameter conversion logic
        if "functions" in model_parameters:
            model_parameters["tools"] = [{"type": "function", "function": func} for func in model_parameters.pop("functions")]
        if "function_call" in model_parameters:
            model_parameters["tool_choice"] = model_parameters.pop("function_call")
        return self._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(model, credentials)
        return super().validate_credentials(model, credentials)

    def _generate(
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
        self._update_credential(model, credentials)
        
        # Add parameter conversion logic
        if "functions" in model_parameters:
            model_parameters["tools"] = [{"type": "function", "function": func} for func in model_parameters.pop("functions")]
        if "function_call" in model_parameters:
            model_parameters["tool_choice"] = model_parameters.pop("function_call")
            
        return super()._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def _wrap_thinking_by_reasoning_content(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        If the reasoning response is from delta.get("reasoning") or delta.get("reasoning_content"),
        we wrap it with HTML think tag.

        :param delta: delta dictionary from LLM streaming response
        :param is_reasoning: is reasoning
        :return: tuple of (processed_content, is_reasoning)
        """

        content = delta.get("content") or ""
        # NOTE(hzw): OpenRouter uses "reasoning" instead of "reasoning_content".
        reasoning_content = delta.get("reasoning") or delta.get("reasoning_content")

        if reasoning_content:
            if not is_reasoning:
                content = "<think>\n" + reasoning_content
                is_reasoning = True
            else:
                content = reasoning_content
        elif is_reasoning and content:
            content = "\n</think>" + content
            is_reasoning = False
        return content, is_reasoning

    def _generate_block_as_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        user: Optional[str] = None,
    ) -> Generator:
        resp = super()._generate(model, credentials, prompt_messages, model_parameters, tools, stop, False, user)
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=resp.message,
                usage=self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens,
                ),
                finish_reason="stop",
            ),
        )

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        self._update_credential(model, credentials)
        return super().get_customizable_model_schema(model, credentials)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        self._update_credential(model, credentials)
        return super().get_num_tokens(model, credentials, prompt_messages, tools)
