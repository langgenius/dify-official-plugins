from collections.abc import Iterator

import pytest
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    UserPromptMessage,
)

from models.llm import llm
from models.llm.wire import Delta, UpstreamServerError

CREDENTIALS = {
    f"{tier}_{key}": value
    for tier in ("capable", "efficient")
    for key, value in {
        "endpoint_url": f"https://{tier}.example/v1",
        "model": f"{tier}-model",
        "api_format": "chat_completions",
    }.items()
}
PLAIN_CHAT = [UserPromptMessage(content="hi")]


@pytest.fixture(autouse=True)
def _no_usage_pricing(monkeypatch: pytest.MonkeyPatch):
    # Usage pricing needs a model schema, which these unit tests do not load.
    monkeypatch.setattr(llm.SwitchyardLargeLanguageModel, "_calc_response_usage", lambda *args: None)


def _model() -> llm.SwitchyardLargeLanguageModel:
    return llm.SwitchyardLargeLanguageModel(model_schemas=[])


def _fails_after(deltas: list[Delta]) -> Iterator[Delta]:
    yield from deltas
    raise UpstreamServerError("stream broke")


def _streams(monkeypatch: pytest.MonkeyPatch, by_model: dict, modes: list | None = None) -> list[str]:
    opened: list[str] = []

    def fake_open_response(upstream, ir, tools, params, stop, stream=True):
        opened.append(upstream.model)
        if modes is not None:
            modes.append(stream)
        return by_model[upstream.model]()

    monkeypatch.setattr(llm, "open_response", fake_open_response)
    return opened


@pytest.mark.parametrize("stream", [True, False])
def test_stream_flag_reaches_the_upstream(monkeypatch: pytest.MonkeyPatch, stream: bool):
    modes: list[bool] = []
    ok = {"efficient-model": lambda: iter([Delta(text="ok"), Delta(finish_reason="stop")])}
    _streams(monkeypatch, ok, modes)
    chunks = list(_model()._invoke("auto", CREDENTIALS, PLAIN_CHAT, {}, stream=stream))
    assert modes == [stream]
    assert chunks[-1].delta.finish_reason == "stop"


def test_stream_failing_before_output_falls_back(monkeypatch: pytest.MonkeyPatch):
    opened = _streams(
        monkeypatch,
        {
            # Usage alone is not output, so this failure still falls back.
            "efficient-model": lambda: _fails_after([Delta(usage=(1, 0))]),
            "capable-model": lambda: iter([Delta(text="ok"), Delta(finish_reason="stop")]),
        },
    )
    chunks = list(_model()._invoke("auto", CREDENTIALS, PLAIN_CHAT, {}))
    assert opened == ["efficient-model", "capable-model"]
    assert {c.model for c in chunks} == {"capable-model"}
    assert "".join(c.delta.message.content for c in chunks) == "ok"


def test_stream_failing_after_output_does_not_fall_back(monkeypatch: pytest.MonkeyPatch):
    opened = _streams(monkeypatch, {"efficient-model": lambda: _fails_after([Delta(text="par")])})
    chunks = _model()._invoke("auto", CREDENTIALS, PLAIN_CHAT, {})
    assert next(chunks).delta.message.content == "par"
    with pytest.raises(UpstreamServerError):
        list(chunks)
    assert opened == ["efficient-model"]


def test_num_tokens_counts_tool_calls_and_definitions():
    model = _model()
    call = AssistantPromptMessage.ToolCall(
        id="c1",
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name="bash", arguments='{"command": "ls -la /var/log"}'
        ),
    )
    tool = PromptMessageTool(name="bash", description="Run a shell command", parameters={"type": "object"})
    plain = model.get_num_tokens("auto", CREDENTIALS, PLAIN_CHAT)
    with_call = model.get_num_tokens("auto", CREDENTIALS, [*PLAIN_CHAT, AssistantPromptMessage(content="", tool_calls=[call])])
    with_tools = model.get_num_tokens("auto", CREDENTIALS, PLAIN_CHAT, [tool])
    assert with_call > plain
    assert with_tools > plain


def test_concurrent_routing_from_greenlets_does_not_collide():
    # dify_plugin monkey-patches threading with gevent, so these threads are greenlets on one
    # OS thread, as plugin requests are at runtime.
    import threading

    ir = llm.to_ir(PLAIN_CHAT)
    algorithm = llm._algorithm({})
    results, errors = [], []

    def route():
        try:
            results.append(llm._route(algorithm, ir, None).selected_model_ids[0])
        except RuntimeError as e:  # includes LibsyError and "running event loop" failures
            errors.append(repr(e))

    threads = [threading.Thread(target=route) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
    assert results == ["efficient"] * 16
