"""Unit tests for the reasoning_effort parameter rule exposed by get_customizable_model_schema.

OpenAI's reasoning models accept more effort levels than low/medium/high: `minimal`
(gpt-5), `none` (gpt-5.1+) and `xhigh` (gpt-5.4+). The plugin is a generic
OpenAI-compatible provider and cannot know which levels a given endpoint supports, so it
offers all of them and lets the upstream endpoint reject what it does not accept.
"""

import pytest

from models.llm.llm import OpenAILargeLanguageModel

EXPECTED_LEVELS = ["none", "minimal", "low", "medium", "high", "xhigh"]


def _reasoning_effort_rule(agent_thought_support):
    llm = OpenAILargeLanguageModel(model_schemas=[])
    entity = llm.get_customizable_model_schema(
        "gpt-5.6-luna",
        {"mode": "chat", "context_size": "922000", "agent_thought_support": agent_thought_support},
    )
    return next((rule for rule in entity.parameter_rules if rule.name == "reasoning_effort"), None)


@pytest.mark.parametrize("agent_thought_support", ["only_thinking_supported", "supported"])
def test_reasoning_effort_exposes_every_openai_level(agent_thought_support):
    rule = _reasoning_effort_rule(agent_thought_support)

    assert rule is not None
    assert rule.options == EXPECTED_LEVELS


def test_reasoning_effort_absent_without_thinking_support():
    assert _reasoning_effort_rule("not_supported") is None
