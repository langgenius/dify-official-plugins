"""Strict inverse of Graphon 0.7.0's text Chat classifier template.

Only categories are JSON-encoded upstream. Never JSON-decode the entire prompt:
that corrupts literal backslashes. Repeated field boundaries are ambiguous and
rejected. These constants intentionally preserve upstream typos and whitespace.
Source: graphon 0.7.0, nodes/question_classifier/template_prompts.py.
"""

import json
from dataclasses import dataclass

from dify_plugin.entities.model.message import PromptMessage, TextPromptMessageContent
from dify_plugin.errors.model import InvokeBadRequestError

QUESTION_CLASSIFIER_SYSTEM_PROMPT = "\n### Job Description',\nYou are a text classification engine that analyzes text data and assigns categories based on user input or automatically determined categories.\n### Task\nYour task is to assign one categories ONLY to the input text and only one category may be assigned returned in the output.\nAdditionally, you need to extract the key words from the text that are related to the classification.\n### Format\nThe input text is in the variable input_text. Categories are specified as a category list with two filed category_id and category_name in the variable categories. Classification instructions may be included to improve the classification accuracy.\n### Constraint\nDO NOT include anything other than the JSON array in your response.\n### Memory\nHere are the chat histories between human and assistant, inside <histories></histories> XML tags.\n<histories>\n{histories}\n</histories>\n"

QUESTION_CLASSIFIER_USER_PROMPT_1 = '\n    {"input_text": ["I recently had a great experience with your company. The service was prompt and the staff was very friendly."],\n    "categories": [{"category_id":"f5660049-284f-41a7-b301-fd24176a711c","category_name":"Customer Service"},{"category_id":"8d007d06-f2c9-4be5-8ff6-cd4381c13c60","category_name":"Satisfaction"},{"category_id":"5fbbbb18-9843-466d-9b8e-b9bfbb9482c8","category_name":"Sales"},{"category_id":"23623c75-7184-4a2e-8226-466c2e4631e4","category_name":"Product"}],\n    "classification_instructions": ["classify the text based on the feedback provided by customer"]}\n'

QUESTION_CLASSIFIER_ASSISTANT_PROMPT_1 = '\n```json\n    {"keywords": ["recently", "great experience", "company", "service", "prompt", "staff", "friendly"],\n    "category_id": "f5660049-284f-41a7-b301-fd24176a711c",\n    "category_name": "Customer Service"}\n```\n'

QUESTION_CLASSIFIER_USER_PROMPT_2 = '\n    {"input_text": ["bad service, slow to bring the food"],\n    "categories": [{"category_id":"80fb86a0-4454-4bf5-924c-f253fdd83c02","category_name":"Food Quality"},{"category_id":"f6ff5bc3-aca0-4e4a-8627-e760d0aca78f","category_name":"Experience"},{"category_id":"cc771f63-74e7-4c61-882e-3eda9d8ba5d7","category_name":"Price"}],\n    "classification_instructions": []}\n'

QUESTION_CLASSIFIER_ASSISTANT_PROMPT_2 = '\n```json\n    {"keywords": ["bad service", "slow", "food", "tip", "terrible", "waitresses"],\n    "category_id": "f6ff5bc3-aca0-4e4a-8627-e760d0aca78f",\n    "category_name": "Experience"}\n```\n'


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
    texts = [message_text(m).strip() for m in messages]
    examples = [
        QUESTION_CLASSIFIER_USER_PROMPT_1,
        QUESTION_CLASSIFIER_ASSISTANT_PROMPT_1,
        QUESTION_CLASSIFIER_USER_PROMPT_2,
        QUESTION_CLASSIFIER_ASSISTANT_PROMPT_2,
    ]
    if texts[1:5] != [example.strip() for example in examples]:
        raise InvokeBadRequestError("Unrecognized classifier examples")
    system_prefix, system_suffix = QUESTION_CLASSIFIER_SYSTEM_PROMPT.strip().split("{histories}")
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
        raise InvokeBadRequestError("Unrecognized or ambiguous classifier field boundaries")
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
