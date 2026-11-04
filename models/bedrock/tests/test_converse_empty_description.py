"""Bedrock Converse rejects empty tool descriptions and empty system blocks.

Bedrock's Converse API validates ``toolSpec.description`` (min length 1) and
system ``text`` (min length 1). Dify's shell layer registers ``shell_*`` tools
with no description, and an empty drive/skill prefix prompt can produce an empty
system message after ``.strip()``. Pre-fix, both were forwarded unchanged and
the request was rejected by boto3 before the model ran.

The fix:
- ``_convert_converse_tool_config`` falls back to the tool name when the
  description is missing, empty, or whitespace-only.
- ``_convert_converse_prompt_messages`` skips system messages that are empty
  after stripping.

These tests pin both behaviors at the unit level (no network).
"""

from __future__ import annotations

import importlib

import pytest

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel
PromptMessageTool = llm_mod.PromptMessageTool
SystemPromptMessage = llm_mod.SystemPromptMessage


def _tool(name: str, description: str) -> PromptMessageTool:
    return PromptMessageTool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": {}},
    )


@pytest.mark.parametrize(
    "description, expected",
    [
        ("", "shell_run"),
        ("   ", "shell_run"),
        ("Get current weather", "Get current weather"),
        ("  Get current weather  ", "Get current weather"),
    ],
)
def test_converse_tool_config_falls_back_to_name_for_empty_description(
    description: str, expected: str
) -> None:
    tool = _tool("shell_run", description)
    config = object.__new__(BedrockLLM)._convert_converse_tool_config(tools=[tool])
    assert config["tools"][0]["toolSpec"]["description"] == expected


def test_converse_tool_config_keeps_non_empty_description() -> None:
    tool = _tool("get_weather", "Get current weather for one city")
    config = object.__new__(BedrockLLM)._convert_converse_tool_config(tools=[tool])
    assert config["tools"][0]["toolSpec"]["description"] == "Get current weather for one city"


@pytest.mark.parametrize(
    "contents, expected_texts",
    [
        (["be brief", "  ", "", "hello"], ["be brief", "hello"]),
        (["  ", ""], []),
        (["only"], ["only"]),
    ],
)
def test_converse_prompt_messages_skips_empty_system_blocks(
    contents: list[str], expected_texts: list[str]
) -> None:
    messages = [SystemPromptMessage(content=c) for c in contents]
    system, _ = object.__new__(BedrockLLM)._convert_converse_prompt_messages(
        prompt_messages=messages,
        model_id="anthropic.claude-5-opus",
        system_cache_checkpoint=False,
        latest_two_messages_cache_checkpoint=False,
    )
    assert [block["text"] for block in system] == expected_texts
