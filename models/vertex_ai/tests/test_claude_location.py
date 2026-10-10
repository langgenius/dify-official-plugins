from anthropic.types import Message, TextBlock, Usage
from dify_plugin.entities.model.message import UserPromptMessage

import models.llm.llm as llm_module
from models.llm.llm import VertexAiLargeLanguageModel


class _FakeMessages:
    def create(self, **kwargs):
        return Message(
            id="msg_test",
            type="message",
            role="assistant",
            model=kwargs["model"],
            content=[TextBlock(type="text", text="ok")],
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(input_tokens=1, output_tokens=1),
        )


def _patch_client(monkeypatch) -> list[str]:
    regions: list[str] = []

    class FakeAnthropicVertex:
        def __init__(self, region, project_id, access_token=None):
            regions.append(region)
            self.messages = _FakeMessages()

    monkeypatch.setattr(llm_module, "AnthropicVertex", FakeAnthropicVertex)
    return regions


def _generate(credentials: dict):
    return VertexAiLargeLanguageModel([])._generate_anthropic(
        "claude-sonnet-4-6",
        credentials,
        [UserPromptMessage(content="hi")],
        {"max_tokens": 16},
        stream=False,
    )


def test_claude_works_when_anthropic_location_is_omitted(monkeypatch):
    # Dify drops optional credential fields that are left blank, so the key is absent.
    regions = _patch_client(monkeypatch)
    result = _generate({"vertex_project_id": "proj", "vertex_location": "europe-west1"})
    assert result.message.content == "ok"
    assert regions == ["europe-west1"]


def test_claude_uses_anthropic_location_when_set(monkeypatch):
    regions = _patch_client(monkeypatch)
    _generate(
        {
            "vertex_project_id": "proj",
            "vertex_location": "europe-west1",
            "vertex_anthropic_location": "us-east5",
        }
    )
    assert regions == ["us-east5"]
