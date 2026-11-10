"""Adapt the known Dify classifier protocol to one TypeSafe Choice request.

No node identity is supplied by Dify: this validates a message protocol, not the
caller. Credentials and clients belong to one invocation, never global state.
"""

import json

from dify_plugin import LargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from typesafe_sdk import (
    Choice,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeClient,
    TypeSafeError,
)

from models.llm.classifier_prompt import message_text, parse_classifier_prompt

MODEL = "jev-1.13.0-only-for-question-classifier"
UPSTREAM_MODELS = {MODEL: "jev-1.13.0"}


def client_for(credentials: dict) -> TypeSafeClient:
    """Require an explicit key so the SDK cannot inherit ambient credentials."""
    key = credentials.get("api_key")
    if not isinstance(key, str) or not key.strip():
        raise InvokeAuthorizationError("TypeSafe AI API key is required")
    return TypeSafeClient(api_key=key, base_url="https://api.typesafe.ai", timeout=30.0)


def api_error(error: TypeSafeError) -> InvokeError:
    """Discard upstream bodies, headers and exception text before Dify sees them."""
    if isinstance(error, TypeSafeAPIConnectionError):
        return InvokeConnectionError("TypeSafe AI connection failed or timed out")
    if isinstance(error, TypeSafeAPIResponseValidationError):
        return InvokeServerUnavailableError("TypeSafe AI returned an invalid response")
    if isinstance(error, TypeSafeAPIError):
        status = error.status
        error_type = {
            400: InvokeBadRequestError,
            404: InvokeBadRequestError,
            422: InvokeBadRequestError,
            401: InvokeAuthorizationError,
            403: InvokeAuthorizationError,
            429: InvokeRateLimitError,
        }.get(status, InvokeServerUnavailableError)
        return error_type(f"TypeSafe AI HTTP {status}")
    return InvokeBadRequestError("Invalid TypeSafe AI request")


class TypeSafeAILargeLanguageModel(LargeLanguageModel):
    """Text-only, predefined classifier adapter; upstream never streams text."""

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult:
        if model not in UPSTREAM_MODELS:
            raise InvokeBadRequestError("Unsupported TypeSafe AI model")
        if tools or stop or model_parameters:
            raise InvokeBadRequestError(
                "Classifier does not support tools, stop or model parameters"
            )
        parsed = parse_classifier_prompt(prompt_messages)
        try:
            # Even the local single-category path requires explicit credentials.
            with client_for(credentials) as client:
                if len(parsed.categories) == 1:
                    choice = next(iter(parsed.categories))
                    input_tokens = output_tokens = 0
                else:
                    response = client.system_one(
                        model=UPSTREAM_MODELS[model],
                        state={"query": parsed.query, "history_text": parsed.history_text},
                        questions={
                            "route": Choice(
                                instructions={
                                    "task": "Classify state.query into exactly one provided category, "
                                    "using state.history_text as conversation context.",
                                    "classification_instructions": parsed.instruction,
                                },
                                criteria=parsed.categories,
                            )
                        },
                    )
                    answer = response.choices.get("route")
                    if answer is None or answer.choice not in parsed.categories:
                        raise InvokeServerUnavailableError(
                            "TypeSafe AI returned an invalid category"
                        )
                    choice = answer.choice
                    input_tokens = response.usage.input_tokens
                    output_tokens = response.usage.output_tokens
                    # The SDK permits absent/null counts; never invent billable usage.
                    if input_tokens is None or output_tokens is None:
                        raise InvokeServerUnavailableError(
                            "TypeSafe AI returned unavailable token usage"
                        )
        except TypeSafeError as error:
            raise api_error(error) from None
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=AssistantPromptMessage(
                content=json.dumps(
                    {
                        "category_id": choice,
                        "category_name": parsed.categories[choice],
                    },
                    ensure_ascii=False,
                )
            ),
            usage=self._calc_response_usage(model, credentials, input_tokens, output_tokens),
        )

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        """Offline budget estimate, not Jev billing or a guaranteed length limit.

        Dify calls this before final rendering; do not require a complete template.
        """
        return self._get_num_tokens_by_gpt2("\n".join(message_text(m) for m in prompt_messages))

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            if model not in UPSTREAM_MODELS:
                raise InvokeBadRequestError("Unsupported TypeSafe AI model")
            with client_for(credentials) as client:
                client.models.list()
        except (TypeSafeError, InvokeError):
            # SDK error text may contain upstream response bodies.
            raise CredentialsValidateFailedError(
                "TypeSafe AI credential validation failed"
            ) from None

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        # Errors are sanitized before reaching the SDK wrapper, which formats str(error).
        return {
            kind: [kind]
            for kind in (
                InvokeAuthorizationError,
                InvokeBadRequestError,
                InvokeConnectionError,
                InvokeRateLimitError,
                InvokeServerUnavailableError,
            )
        }
