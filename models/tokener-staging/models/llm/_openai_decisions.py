import json
from hashlib import sha256

from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeServerUnavailableError

from models.llm._classifier_prompt import parse_classifier_prompt

MODEL = "gpt-6-luna-only-for-question-classifier"
UPSTREAM_MODEL = "gpt-6-luna"


def generate(
    llm,
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
    payload: dict = {
        "model": UPSTREAM_MODEL,
        "input": json.dumps(
            {"query": parsed.query, "history_text": parsed.history_text},
            ensure_ascii=False,
        ),
        "questions": [
            {
                "type": "choice",
                "name": "route",
                "instructions": (
                    "Classify input.query into exactly one provided category, "
                    "using input.history_text as conversation context.\n" + parsed.instruction
                ),
                "choices": [
                    {"value": category_id, "description": description}
                    for category_id, description in parsed.categories.items()
                ],
            }
        ],
    }
    if user:
        payload["safety_identifier"] = sha256(user.encode()).hexdigest()
    response = llm._post("decisions", credentials, payload)
    answers = response.get("answers")
    if not isinstance(answers, list) or len(answers) != 1 or not isinstance(answers[0], dict):
        raise InvokeServerUnavailableError("OpenAI Decisions returned an invalid answer")
    answer = answers[0]
    if answer.get("type") == "refusal":
        raise InvokeServerUnavailableError("OpenAI Decisions refused to classify the input")
    choice = answer.get("choice")
    if (
        answer.get("type") != "choice"
        or answer.get("name") not in (None, "route")
        or not isinstance(choice, str)
        or choice not in parsed.categories
    ):
        raise InvokeServerUnavailableError("OpenAI Decisions returned an invalid category")
    usage = response.get("usage")
    input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
    output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
    if any(type(count) is not int or count < 0 for count in (input_tokens, output_tokens)):
        raise InvokeServerUnavailableError("OpenAI Decisions returned invalid token usage")
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
