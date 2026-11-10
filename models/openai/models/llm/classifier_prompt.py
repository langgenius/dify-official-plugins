"""Recover fields from Graphon 0.7.0's text Chat classifier template.

Only categories are JSON-encoded upstream. Never JSON-decode the entire prompt:
that corrupts literal backslashes. Repeated field boundaries are ambiguous and
rejected. The system template preserves upstream typos and whitespace.
Source: graphon 0.7.0, nodes/question_classifier/template_prompts.py.
Adapted from the TypeSafe AI plugin's classifier_prompt.py.
"""

import json
from dataclasses import dataclass

from dify_plugin.entities.model.message import PromptMessage, TextPromptMessageContent
from dify_plugin.errors.model import InvokeBadRequestError

QUESTION_CLASSIFIER_SYSTEM_PROMPT = "\n### Job Description',\nYou are a text classification engine that analyzes text data and assigns categories based on user input or automatically determined categories.\n### Task\nYour task is to assign one categories ONLY to the input text and only one category may be assigned returned in the output.\nAdditionally, you need to extract the key words from the text that are related to the classification.\n### Format\nThe input text is in the variable input_text. Categories are specified as a category list with two filed category_id and category_name in the variable categories. Classification instructions may be included to improve the classification accuracy.\n### Constraint\nDO NOT include anything other than the JSON array in your response.\n### Memory\nHere are the chat histories between human and assistant, inside <histories></histories> XML tags.\n<histories>\n{histories}\n</histories>\n"


@dataclass(frozen=True)
class ClassifierInput:
    query: str
    history_text: str
    instruction: str
    categories: dict[str, str]


def message_text(message: PromptMessage) -> str:
    """Accept plain text or its single-text-block SDK representation only."""
    if getattr(message, "tool_calls", None):
        raise InvokeBadRequestError("Classifier messages cannot contain tool calls")
    content = message.content
    if isinstance(content, str):
        return content
    if (
        isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], TextPromptMessageContent)
    ):
        return content[0].data
    raise InvokeBadRequestError("Only text classifier messages are supported")


def parse_classifier_prompt(messages: list[PromptMessage]) -> ClassifierInput:
    """Recover rendered fields; refuse unknown templates or ambiguous boundaries."""
    roles = ["system", "user", "assistant", "user", "assistant", "user"]
    if len(messages) != 6 or [m.role.value for m in messages] != roles:
        raise InvokeBadRequestError("Expected Graphon 0.7.0 Chat classifier messages")
    # The four examples do not carry invocation fields; their wording is ignored.
    texts = [message_text(m).strip() for m in messages]
    system_prefix, system_suffix = QUESTION_CLASSIFIER_SYSTEM_PROMPT.strip().split(
        "{histories}"
    )
    if not texts[0].startswith(system_prefix) or not texts[0].endswith(system_suffix):
        raise InvokeBadRequestError("Unrecognized classifier system template")
    history = texts[0][len(system_prefix) : -len(system_suffix)]
    prefix = '{"input_text": ["'
    boundary = '"],\n    "categories": '
    instruction_boundary = ',\n    "classification_instructions": ["'
    suffix = '"]}'
    body = texts[-1]
    if (
        not body.startswith(prefix)
        or not body.endswith(suffix)
        or body.count(boundary) != 1
        or body.count(instruction_boundary) != 1
    ):
        raise InvokeBadRequestError(
            "Unrecognized or ambiguous classifier field boundaries"
        )
    query, remainder = body[len(prefix) : -len(suffix)].split(boundary)
    try:
        categories, end = json.JSONDecoder().raw_decode(remainder)
    except ValueError:
        raise InvokeBadRequestError("Invalid classifier categories JSON") from None
    if not remainder[end:].startswith(instruction_boundary):
        raise InvokeBadRequestError("Unrecognized classifier category boundary")
    instruction = remainder[end + len(instruction_boundary) :]
    if not isinstance(categories, list) or not categories:
        raise InvokeBadRequestError("Classifier requires a nonempty category array")
    mapping = {}
    for category in categories:
        if (
            not isinstance(category, dict)
            or not isinstance(category.get("category_id"), str)
            or not category["category_id"]
            or not isinstance(category.get("category_name"), str)
            or category["category_id"] in mapping
        ):
            raise InvokeBadRequestError(
                "Classifier requires unique nonempty string IDs and string names"
            )
        mapping[category["category_id"]] = category["category_name"]
    return ClassifierInput(query, history, instruction, mapping)
