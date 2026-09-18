"""Local smoke test for the OpenCode Go plugin LLM implementation."""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from models.llm.llm import OpenCodeGoLargeLanguageModel  # noqa: E402
from dify_plugin.entities.model.message import UserPromptMessage  # noqa: E402

API_KEY = __import__("os").environ.get("OPENCODE_GO_API_KEY", "")

MODELS_TO_TEST = [
    "glm-5.3-flash",
    "mimo-v2.5",
    "kimi-k2.6",
    "deepseek-v4-flash",
    "qwen3.8-flash",
    "hy3",
]


def make_model() -> OpenCodeGoLargeLanguageModel:
    # Minimal instance; model_schemas can be empty for invoke path that uses credentials defaults.
    return OpenCodeGoLargeLanguageModel(model_schemas=[])


def test_sync(model_id: str) -> None:
    llm = make_model()
    credentials = {"api_key": API_KEY}
    result = llm._invoke(
        model=model_id,
        credentials=credentials,
        prompt_messages=[UserPromptMessage(content="Reply with exactly: OK")],
        model_parameters={"max_tokens": 64, "temperature": 0.1},
        tools=None,
        stop=None,
        stream=False,
        user="local-test-user",
    )
    text = result.message.content if result.message else ""
    print(f"SYNC  {model_id:32s} ok content={text!r} usage={result.usage}")


def test_stream(model_id: str) -> None:
    llm = make_model()
    credentials = {"api_key": API_KEY}
    gen = llm._invoke(
        model=model_id,
        credentials=credentials,
        prompt_messages=[UserPromptMessage(content="Count 1 2 3 briefly.")],
        model_parameters={"max_tokens": 64, "temperature": 0.1},
        tools=None,
        stop=None,
        stream=True,
        user="local-test-user",
    )
    chunks = 0
    text_parts: list[str] = []
    for chunk in gen:
        chunks += 1
        if getattr(chunk, "delta", None) and chunk.delta.message:
            content = chunk.delta.message.content
            if content:
                text_parts.append(content if isinstance(content, str) else str(content))
    text = "".join(text_parts)
    preview = text[:80] + ("..." if len(text) > 80 else "")
    print(f"STREAM {model_id:32s} ok chunks={chunks} text={preview!r}")


def test_validate(model_id: str) -> None:
    llm = make_model()
    llm.validate_credentials(model=model_id, credentials={"api_key": API_KEY})
    print(f"VALID {model_id:32s} ok")


def main() -> int:
    failed = 0
    print("=== validate_credentials ===")
    try:
        test_validate("glm-5.3-flash")
    except Exception:
        failed += 1
        traceback.print_exc()

    print("\n=== non-stream invoke ===")
    for mid in MODELS_TO_TEST:
        try:
            test_sync(mid)
        except Exception as e:
            failed += 1
            print(f"SYNC  {mid:32s} FAIL {type(e).__name__}: {e}")

    print("\n=== stream invoke ===")
    for mid in ["glm-5.3-flash", "kimi-k2.6", "qwen3.8-flash"]:
        try:
            test_stream(mid)
        except Exception as e:
            failed += 1
            print(f"STREAM {mid:32s} FAIL {type(e).__name__}: {e}")

    print(f"\nDONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
