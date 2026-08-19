"""Pure transformations used by the MiniMax text embedding adapter.

Keep provider I/O in ``text_embedding.py`` and put deterministic data-to-data
operations here. This makes the batching behavior easy to reason about and test
without an API client.
"""

from collections.abc import Callable, Mapping, Sequence

# embo-01 declares context_size: 4096. Keep a safety margin so token counting
# imprecision (gpt2 tokenizer over-estimates CJK text) never overflows it.
MAX_TOKENS_PER_REQUEST = 3500

# Default cap on the number of texts sent per embedding request. Kept at 1 to
# match upstream behavior: batching only engages when users raise the
# ``batch_size`` credential. Raising it trades fewer API calls (avoids MiniMax's
# per-minute rate limit) against larger requests (bounded by the context window).
DEFAULT_BATCH_SIZE = 1


def resolve_batch_size(credentials: Mapping | None, default: int = DEFAULT_BATCH_SIZE) -> int:
    """Read the ``batch_size`` credential, falling back to ``default`` on bad input."""
    if not credentials:
        return default
    try:
        return max(1, int(credentials.get("batch_size", default)))
    except (TypeError, ValueError):
        return default


def batch_texts(
    texts: Sequence[str],
    batch_size: int,
    count_tokens: Callable[[str], int],
    max_tokens_per_request: int = MAX_TOKENS_PER_REQUEST,
) -> list[list[str]]:
    """Split ``texts`` into request-sized batches.

    Each batch is bounded by both ``batch_size`` (max texts) and
    ``max_tokens_per_request`` (max estimated tokens), whichever is hit first.
    Text order is preserved so vector results can be concatenated back.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for text in texts:
        tokens = count_tokens(text)
        if current and (len(current) >= batch_size or current_tokens + tokens > max_tokens_per_request):
            batches.append(current)
            current = [text]
            current_tokens = tokens
        else:
            current.append(text)
            current_tokens += tokens
    if current:
        batches.append(current)
    return batches
