"""
Unit tests for the _wrap_thinking_by_reasoning_content logic in the Tongyi plugin.

We extract the method logic directly to avoid complex SDK dependency mocking.
The test verifies the exact same algorithm that exists in models/llm/llm.py.
"""


def _wrap_thinking_by_reasoning_content(delta: dict, is_reasoning: bool) -> tuple:
    """
    Exact copy of TongyiLargeLanguageModel._wrap_thinking_by_reasoning_content
    from models/llm/llm.py for isolated unit testing.
    """
    content = delta.get("content") or ""
    if isinstance(content, list) and content:
        content = content[0].get("text") if isinstance(content[0], dict) else ""
    else:
        content = str(content)
    reasoning_content = delta.get("reasoning_content") or ""
    try:
        if isinstance(reasoning_content, list):
            reasoning_content = "\n".join(map(str, reasoning_content))
        elif not isinstance(reasoning_content, str):
            reasoning_content = str(reasoning_content)

        output = ""
        if reasoning_content:
            if not is_reasoning:
                # Open a think block on first reasoning token
                output += f"<think>\n{reasoning_content}"
                is_reasoning = True
            else:
                # Continue streaming inside the think block
                output += reasoning_content

        if is_reasoning:
            if not reasoning_content and not content:
                # No reasoning or content token, close the think block
                is_reasoning = False
                output += "\n</think>"
            # Handle edge case: both reasoning_content and content are non-empty
            # in the same chunk (DashScope/Bailian API occasionally does this at
            # the transition boundary between reasoning and content phases)
            if content:
                is_reasoning = False
                output += f"\n</think>{content}"
        elif content:
            # No reasoning token and not in a reasoning block
            output += content
    except Exception as ex:
        raise ValueError(f"[wrap_thinking_by_reasoning_content] {ex}") from ex
    return output, is_reasoning


def test_wrap_reasoning_start():
    """Test that reasoning_content starts a think block correctly."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "Let me think", "content": ""}, False
    )
    assert out == "<think>\nLet me think"
    assert is_reasoning is True


def test_wrap_reasoning_continue():
    """Test that subsequent reasoning chunks continue inside the think block."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "step 2", "content": ""}, True
    )
    assert out == "step 2"
    assert is_reasoning is True


def test_wrap_reasoning_close_on_content():
    """Test that the think block closes when content arrives after reasoning."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "", "content": "Hello"}, True
    )
    assert out == "\n</think>Hello"
    assert is_reasoning is False


def test_wrap_plain_content_no_reasoning():
    """Test that plain content passes through when not in reasoning mode."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"content": "plain text", "reasoning_content": ""}, False
    )
    assert out == "plain text"
    assert is_reasoning is False


def test_wrap_reasoning_close_on_empty_delta():
    """Test that an empty delta while reasoning closes the think block."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "", "content": ""}, True
    )
    assert out == "\n</think>"
    assert is_reasoning is False


def test_wrap_reasoning_and_content_both_not_empty():
    """
    Test the edge case where both reasoning_content and content are non-empty
    in the same streaming chunk. This happens occasionally with DashScope/Bailian
    API at the transition boundary between reasoning and content phases.
    """
    is_reasoning = False

    # 1) start reasoning
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "thinking step 1", "content": ""}, is_reasoning
    )
    assert out == "<think>\nthinking step 1"
    assert is_reasoning is True

    # 2) continue reasoning
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": ", step 2", "content": ""}, is_reasoning
    )
    assert out == ", step 2"
    assert is_reasoning is True

    # 3) edge case: both reasoning_content and content are non-empty
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": ", final thought.", "content": "Hello! I am"}, is_reasoning
    )
    assert out == ", final thought.\n</think>Hello! I am"
    assert is_reasoning is False

    # 4) subsequent plain content should pass through normally
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "", "content": " a helpful assistant."}, is_reasoning
    )
    assert out == " a helpful assistant."
    assert is_reasoning is False


def test_wrap_reasoning_and_content_both_not_empty_at_start():
    """
    Test the edge case where reasoning_content and content are both non-empty
    in the very first chunk (is_reasoning starts as False).
    """
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "quick thought", "content": "Answer"}, False
    )
    assert out == "<think>\nquick thought\n</think>Answer"
    assert is_reasoning is False


def test_wrap_reasoning_content_as_list():
    """Test that reasoning_content as a list is handled correctly."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": ["line1", "line2"], "content": ""}, False
    )
    assert out == "<think>\nline1\nline2"
    assert is_reasoning is True


def test_wrap_content_as_list():
    """Test that content as a list of dicts is handled correctly."""
    out, is_reasoning = _wrap_thinking_by_reasoning_content(
        {"reasoning_content": "", "content": [{"text": "from list"}]}, False
    )
    assert out == "from list"
    assert is_reasoning is False
