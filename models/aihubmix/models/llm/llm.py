import logging
from collections.abc import Generator
from typing import Optional, Union, Any, cast
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool, AssistantPromptMessage
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from .anthropic import AnthropicLargeLanguageModel
from .google import GoogleLargeLanguageModel
from .openai_response import AihubmixOpenAIResponses

# 如果两个类都继承自同一个基类，可以使用相同的初始化方式
model_schemas = []  # 或者从某处获取适当的模型模式
anthropic_llm = AnthropicLargeLanguageModel(model_schemas)
google_llm = GoogleLargeLanguageModel(model_schemas)
logger = logging.getLogger(__name__)

# thinking models compatibility for max_completion_tokens (all starting with "o" or "gpt-5")
THINKING_SERIES_COMPATIBILITY = ("o", "gpt-5")
RESPONSE_SERIES_COMPATIBILITY = ("gpt-5-codex", "gpt-5-pro", "o3-pro")


class AihubmixLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = "https://aihubmix.com/v1"
        credentials["mode"] = self.get_model_mode(model).value
        credentials["function_calling_type"] = "tool_call"
        credentials["extra_headers"] = {
            "APP-Code": "Dify2025"
        }

    def _dispatch_to_appropriate_model(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None
    ) -> Union[LLMResult, Generator]:
        """根据模型名称分发到适当的模型处理类"""
        # 检查模型名称是否以 "claude" 开头
        if model.startswith("claude"):
            return anthropic_llm._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)
        
        # 检查模型名称是否以 "gemini" 开头且不以 "-nothink" 或 "-search" 结尾
        if model.startswith("gemini") and not (model.endswith("-nothink") or model.endswith("-search")):
            return google_llm._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)
        
        # thinking models compatibility for max_completion_tokens (all starting with "o" or "gpt-5")
        if model.startswith(THINKING_SERIES_COMPATIBILITY):
            if "max_tokens" in model_parameters:
                model_parameters["max_completion_tokens"] = model_parameters[
                    "max_tokens"
                ]
                del model_parameters["max_tokens"]
        # 走 response 接口，其他模型走 generate 接口
        if model.startswith(RESPONSE_SERIES_COMPATIBILITY):
            # 使用 Responses API（委托给 openai_response 封装；支持流式/非流式）
            resp_handler = AihubmixOpenAIResponses(credentials)
            compute_usage = lambda pt, ct: self._calc_response_usage(
                model=model,
                credentials=credentials,
                prompt_tokens=pt,
                completion_tokens=ct,
            )
            if stream:
                return resp_handler.stream_llm_chunks(
                    model=model,
                    prompt_messages=prompt_messages,
                    model_parameters=model_parameters,
                    compute_usage=compute_usage,
                    user=user,
                )

            return resp_handler.create_llm_result(
                model=model,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                compute_usage=compute_usage,
                user=user,
            )
        
        # 默认使用父类的生成方法
        return super()._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

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
        try:
            self._update_credential(model, credentials)
            enable_thinking = model_parameters.pop("enable_thinking", None)
            if enable_thinking is not None:
                model_parameters["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}

            # 将自定义的 enable_stream 参数映射到本地 stream 标志，避免把未知参数透传给上游
            enable_stream = model_parameters.pop("enable_stream", None)
            if enable_stream is not None:
                stream = bool(enable_stream)

            return self._dispatch_to_appropriate_model(
                model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
            )
        except Exception as e:
            # 记录异常信息
            logger.error(f"Error invoking model {model}: {str(e)}")
            
            # 根据异常类型映射到统一的错误类型
            for error_type, exception_types in self._invoke_error_mapping.items():
                if any(isinstance(e, exc_type) for exc_type in exception_types):
                    raise error_type(str(e))
            
            # 如果没有匹配的错误类型，则抛出原始异常
            raise InvokeError(f"Unexpected error: {str(e)}")

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._update_credential(model, credentials)
        return super().validate_credentials(model, credentials)

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
    
    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [Exception],
            InvokeServerUnavailableError: [Exception],
            InvokeRateLimitError: [Exception],
            InvokeAuthorizationError: [Exception],
            InvokeBadRequestError: [Exception],
        }

    
    