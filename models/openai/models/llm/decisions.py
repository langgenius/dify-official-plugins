"""Adapt the Dify text classifier protocol to OpenAI Decisions."""

import json

from openai import OpenAI

from dify_plugin import LargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeServerUnavailableError

from ..common_openai import _user_digest
from .classifier_prompt import parse_classifier_prompt

MODEL = "gpt-6-luna-only-for-question-classifier"
UPSTREAM_MODEL = "gpt-6-luna"


def generate(
    llm: LargeLanguageModel,
    client: OpenAI,
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    model_parameters: dict,
    tools: list[PromptMessageTool] | None,
    stop: list[str] | None,
    user: str | None,
) -> LLMResult:
    if tools or stop or model_parameters:
        raise InvokeBadRequestError(
            "OpenAI Decisions classifier does not support tools, stop or model parameters"
        )
    parsed = parse_classifier_prompt(prompt_messages)
    response = client.decisions.create(
        model=UPSTREAM_MODEL,
        input=json.dumps(
            {"query": parsed.query, "history_text": parsed.history_text},
            ensure_ascii=False,
        ),
        questions=[
            {
                "type": "choice",
                "name": "route",
                "instructions": (
                    "Classify input.query into exactly one provided category, "
                    "using input.history_text as conversation context.\n"
                    + parsed.instruction
                ),
                "choices": [
                    {"value": category_id, "description": description}
                    for category_id, description in parsed.categories.items()
                ],
            }
        ],
        **({"safety_identifier": _user_digest(user)} if user else {}),
    )
    answers = getattr(response, "answers", None)
    if not isinstance(answers, list) or len(answers) != 1:
        raise InvokeServerUnavailableError(
            "OpenAI Decisions returned an invalid answer"
        )
    answer = answers[0]
    if getattr(answer, "type", None) == "refusal":
        raise InvokeServerUnavailableError(
            "OpenAI Decisions refused to classify the input"
        )
    choice = getattr(answer, "choice", None)
    if (
        getattr(answer, "type", None) != "choice"
        or getattr(answer, "name", None) != "route"
        or not isinstance(choice, str)
        or choice not in parsed.categories
    ):
        raise InvokeServerUnavailableError(
            "OpenAI Decisions returned an invalid category"
        )
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if any(
        type(count) is not int or count < 0 for count in (input_tokens, output_tokens)
    ):
        raise InvokeServerUnavailableError(
            "OpenAI Decisions returned invalid token usage"
        )
    return LLMResult(
        model=model,
        prompt_messages=prompt_messages,
        message=AssistantPromptMessage(
            content=json.dumps(
                {"category_id": choice, "category_name": parsed.categories[choice]},
                ensure_ascii=False,
            )
        ),
        usage=llm._calc_response_usage(model, credentials, input_tokens, output_tokens),
    )
