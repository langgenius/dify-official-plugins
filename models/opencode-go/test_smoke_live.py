"""Live smoke tests against OpenCode Go. Requires OPENCODE_GO_API_KEY env var.

Usage:
  $env:OPENCODE_GO_API_KEY='sk-...'
  python test_smoke_live.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Strip proxies that can force CONNECT + gevent SSL recursion on Windows.
for _k in list(os.environ):
    if "proxy" in _k.lower():
        del os.environ[_k]

# Import dify_plugin first so gevent monkeypatch runs before urllib3 SSL.
import dify_plugin  # noqa: E402,F401
from models.llm.llm import OpenCodeGoLargeLanguageModel  # noqa: E402
from dify_plugin.entities.model.message import UserPromptMessage  # noqa: E402
from models.llm.session_headers import resolve_protocol  # noqa: E402

API_KEY = os.environ.get("OPENCODE_GO_API_KEY", "")

CHAT_MODELS = [
    "glm-5.3-flash",
    "qwen3.8-flash",
    "minimax-m3",
    "kimi-k2.6",
    "mimo-v2.5",
]
ANTHROPIC_MODELS = ["union-alpha"]
RESPONSES_MODELS = ["grok-4.6", "gpt-5.6-luna"]


def make_model() -> OpenCodeGoLargeLanguageModel:
    return OpenCodeGoLargeLanguageModel(model_schemas=[])


def _message_preview(result) -> str:
    msg = getattr(result, "message", None)
    if msg is None:
        return "None"
    content = msg.content
    tools = getattr(msg, "tool_calls", None) or []
    tool_note = ""
    if tools:
        tool_note = f" tools={[t.function.name for t in tools]}"
    if content is None or content == "":
        # Some gateways only fill reasoning / empty text with usage still charged.
        return f"content={content!r}{tool_note} raw_keys={list(getattr(msg,'opaque_body',None) or {} )}"
    return f"text={str(content)[:80]!r}{tool_note}"


def run_one(model_id: str, stream: bool) -> tuple[bool, str]:
    llm = make_model()
    credentials = {"api_key": API_KEY}
    params = {"max_tokens": 64, "temperature": 0.1}
    try:
        result = llm._invoke(
            model=model_id,
            credentials=credentials,
            prompt_messages=[UserPromptMessage(content="Reply with exactly: OK")],
            model_parameters=params,
            tools=None,
            stop=None,
            stream=stream,
            user="smoke-test",
        )
        if stream:
            chunks = 0
            texts: list[str] = []
            for chunk in result:
                chunks += 1
                delta = getattr(chunk, "delta", None)
                if delta and delta.message and delta.message.content:
                    content = delta.message.content
                    texts.append(content if isinstance(content, str) else str(content))
            preview = ("".join(texts) or "")[:80]
            if chunks == 0:
                return False, "stream produced 0 chunks"
            return True, f"stream chunks={chunks} text={preview!r}"
        usage = result.usage
        detail = (
            f"{_message_preview(result)} "
            f"usage={usage.prompt_tokens}/{usage.completion_tokens}"
        )
        # Success if we got a completed HTTP path with usage or content.
        if usage.prompt_tokens or usage.completion_tokens or result.message:
            return True, detail
        return False, f"empty result {detail}"
    except Exception as ex:
        return False, f"{type(ex).__name__}: {ex}"


def main() -> int:
    if not API_KEY:
        print("OPENCODE_GO_API_KEY not set")
        return 2

    matrix: list[tuple[str, str, bool, str]] = []
    plans = (
        [(m, "chat") for m in CHAT_MODELS]
        + [(m, "anthropic") for m in ANTHROPIC_MODELS]
        + [(m, "responses") for m in RESPONSES_MODELS]
    )
    for model_id, expected in plans:
        got = resolve_protocol(model_id, {})
        if got != expected:
            matrix.append((model_id, f"route:{expected}", False, f"resolved={got}"))
            continue
        for stream in (False, True):
            ok, detail = run_one(model_id, stream)
            matrix.append((model_id, "stream" if stream else "sync", ok, detail))
            print(f"{'OK' if ok else 'FAIL':4} {model_id:28} {'stream' if stream else 'sync':6} {detail}")

    # union-alpha must fail on chat (documented)
    print("--- union-alpha via chat (expect fail) ---")
    try:
        llm = make_model()
        llm._invoke(
            model="union-alpha",
            credentials={"api_key": API_KEY, "api_protocol": "chat"},
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters={"max_tokens": 16},
            stream=False,
            user="smoke-test",
        )
        print("UNEXPECTED: union-alpha chat succeeded")
        matrix.append(("union-alpha", "chat-should-fail", False, "unexpected success"))
    except Exception as ex:
        print(f"EXPECTED FAIL union-alpha chat: {type(ex).__name__}: {str(ex)[:160]}")
        matrix.append(("union-alpha", "chat-should-fail", True, type(ex).__name__))

    failed = [row for row in matrix if not row[2]]
    # Region-restricted upstreams from this host are environmental, not plugin bugs.
    region_fail = [
        row
        for row in failed
        if "region" in row[3].lower() or "unsupported_country" in row[3].lower()
    ]
    real_failed = [row for row in failed if row not in region_fail]
    print("\n=== SUMMARY ===")
    print(f"total={len(matrix)} failed={len(failed)} region_blocked={len(region_fail)} real_failed={len(real_failed)}")
    for row in failed:
        kind = "REGION" if row in region_fail else "FAIL"
        print(kind, row)
    return 1 if real_failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
