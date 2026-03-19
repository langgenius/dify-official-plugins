from models.llm.llm import OpenAILargeLanguageModel


def test_wrap_reasoning_with_new_key_streaming():
    m = OpenAILargeLanguageModel(model_schemas=[])
    is_reasoning = False

    # 1) start reasoning with new key 'reasoning'
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"reasoning": "A"}, is_reasoning)
    assert out == "<think>\nA"
    assert is_reasoning is True

    # 2) continue reasoning
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"reasoning": "B"}, is_reasoning)
    assert out == "B"
    assert is_reasoning is True

    # 3) close reasoning block when normal content arrives
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"content": "Hello"}, is_reasoning)
    assert out == "\n</think>Hello"
    assert is_reasoning is False


def test_wrap_reasoning_with_legacy_key_streaming():
    m = OpenAILargeLanguageModel(model_schemas=[])
    is_reasoning = False

    # 1) start reasoning with legacy key 'reasoning_content'
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"reasoning_content": "X"}, is_reasoning)
    assert out == "<think>\nX"
    assert is_reasoning is True

    # 2) continue reasoning
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"reasoning_content": "Y"}, is_reasoning)
    assert out == "Y"
    assert is_reasoning is True

    # 3) close reasoning block on next plain content
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"content": "Z"}, is_reasoning)
    assert out == "\n</think>Z"
    assert is_reasoning is False


def test_wrap_reasoning_end_without_followup_content():
    m = OpenAILargeLanguageModel(model_schemas=[])
    # reasoning already started
    is_reasoning = True

    # delta without reasoning/content should just close the block
    out, is_reasoning = m._wrap_thinking_by_reasoning_content({}, is_reasoning)
    assert out == "\n</think>"
    assert is_reasoning is False


def test_wrap_plain_content_when_not_in_reasoning():
    m = OpenAILargeLanguageModel(model_schemas=[])
    is_reasoning = False

    out, is_reasoning = m._wrap_thinking_by_reasoning_content({"content": "plain"}, is_reasoning)
    assert out == "plain"
    assert is_reasoning is False
