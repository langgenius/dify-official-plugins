from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.text_embedding._functional import (
    DEFAULT_BATCH_SIZE,
    MAX_TOKENS_PER_REQUEST,
    batch_texts,
    resolve_batch_size,
)


def test_batch_texts_respects_batch_size_and_preserves_order() -> None:
    texts = [f"t{i}" for i in range(25)]

    batches = batch_texts(texts, 10, lambda _: 5)

    assert [len(b) for b in batches] == [10, 10, 5]
    assert [t for b in batches for t in b] == texts


def test_batch_texts_splits_by_token_budget() -> None:
    # 3 texts of 1200 tokens: the third overflows MAX_TOKENS_PER_REQUEST (3500)
    batches = batch_texts(["a", "b", "c"], 10, lambda _: 1200)

    assert [len(b) for b in batches] == [2, 1]


def test_batch_texts_keeps_oversized_single_text_unsplit() -> None:
    # A single text larger than the budget cannot be split further; it must not be dropped.
    batches = batch_texts(["huge"], 10, lambda _: MAX_TOKENS_PER_REQUEST + 1)

    assert batches == [["huge"]]


def test_batch_texts_empty_input() -> None:
    assert batch_texts([], 10, lambda _: 1) == []


def test_batch_texts_batch_size_one_degrades_gracefully() -> None:
    batches = batch_texts(["a", "b", "c"], 1, lambda _: 1)

    assert [len(b) for b in batches] == [1, 1, 1]


def test_batch_texts_rejects_invalid_batch_size() -> None:
    try:
        batch_texts(["a"], 0, lambda _: 1)
    except ValueError:
        return
    raise AssertionError("batch_size < 1 should raise ValueError")


def test_default_batch_size_is_conservative() -> None:
    # Default must match upstream behavior: one text per request.
    assert DEFAULT_BATCH_SIZE == 1
    assert MAX_TOKENS_PER_REQUEST < 4096  # context_size declared in embo-01.yaml


def test_resolve_batch_size_from_credentials() -> None:
    assert resolve_batch_size(None) == 1
    assert resolve_batch_size({}) == 1
    assert resolve_batch_size({"batch_size": "10"}) == 10
    assert resolve_batch_size({"batch_size": 10}) == 10
    assert resolve_batch_size({"batch_size": "0"}) == 1  # clamped to >= 1
    assert resolve_batch_size({"batch_size": "abc"}) == 1  # bad input falls back
    assert resolve_batch_size({"other": "x"}, default=7) == 7
