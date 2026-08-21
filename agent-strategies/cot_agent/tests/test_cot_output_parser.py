import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import AssistantPromptMessage
from dify_plugin.interfaces.agent import AgentScratchpadUnit

from output_parser.cot_output_parser import (
    CotAgentOutputParser,
    ReactChunk,
    ReactState,
    parse_action,
)


def _chunks(*contents: str) -> list[LLMResultChunk]:
    return [
        LLMResultChunk(
            model="test-model",
            delta=LLMResultChunkDelta(
                index=0, message=AssistantPromptMessage(content=content), usage=None
            ),
        )
        for content in contents
    ]


def _parse(*contents: str) -> list:
    usage_dict: dict = {"usage": None}
    return list(CotAgentOutputParser.handle_react_stream_output(_chunks(*contents), usage_dict))


class TestParseAction(unittest.TestCase):
    def test_flat_valid_action(self):
        action = parse_action('{"action": "webSearch", "action_input": {"query": "x"}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "webSearch")
        self.assertEqual(action.action_input, {"query": "x"})

    def test_tool_call_wrapper(self):
        # Issue #3699: the model wraps the payload in an outer "tool_call" key
        raw = (
            '{"tool_call": {"thought": "获取。", "action": "webSearch", '
            '"action_input": {"input": "上海银行"}}}'
        )
        action = parse_action(raw)
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "webSearch")
        self.assertEqual(action.action_input, {"input": "上海银行"})

    def test_wrapper_key_order_does_not_clobber_name(self):
        # "thought" must never be misread as the tool name, in any key order
        raw = (
            '{"tool_call": {"action": "webSearch", "thought": "reasoning", '
            '"action_input": {"input": "x"}}}'
        )
        action = parse_action(raw)
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "webSearch")

    def test_input_only_is_not_an_action(self):
        self.assertIsNone(parse_action('{"input": "x"}'))

    def test_non_string_name_is_not_an_action(self):
        self.assertIsNone(parse_action('{"action": {"nested": 1}, "action_input": "y"}'))

    def test_empty_name_is_not_an_action(self):
        self.assertIsNone(parse_action('{"action": "   ", "action_input": {}}'))

    def test_missing_input_defaults_to_empty_dict(self):
        # parameterless tools may omit the input entirely
        action = parse_action('{"action": "get_time"}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_input, {})

    def test_cohere_single_item_list(self):
        action = parse_action('[{"action": "t", "action_input": {}}]')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "t")

    def test_multi_item_list_is_not_an_action(self):
        self.assertIsNone(parse_action('[{"a": 1}, {"b": 2}]'))

    def test_invalid_json_is_not_an_action(self):
        self.assertIsNone(parse_action("not json"))
        self.assertIsNone(parse_action("42"))

    def test_arbitrary_blob_without_input_key_is_not_an_action(self):
        # a JSON blob quoted inside a thought must not become a tool call
        self.assertIsNone(parse_action('{"foo": "bar"}'))

    def test_legacy_unknown_keys_with_input(self):
        action = parse_action('{"my_tool": "search", "my_input": {"q": 1}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "search")
        self.assertEqual(action.action_input, {"q": 1})

    def test_name_is_stripped(self):
        action = parse_action('{"action": " webSearch ", "action_input": {}}')
        self.assertEqual(action.action_name, "webSearch")

    def test_alias_keys(self):
        action = parse_action('{"tool_name": "t2", "arguments": {"q": 1}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "t2")
        self.assertEqual(action.action_input, {"q": 1})

    def test_tool_calls_list_wrapper(self):
        action = parse_action('{"tool_calls": [{"action": "t3", "action_input": {}}]}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "t3")

    def test_name_keys_are_case_insensitive(self):
        action = parse_action('{"Action": "get_time"}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "get_time")
        self.assertEqual(action.action_input, {})

    def test_function_dict_without_name_is_not_unwrapped(self):
        # a "function" dict without a string "name" is not an OpenAI-style
        # envelope, so it must not shadow a real name key
        action = parse_action('{"function": {"other": 1}, "tool_name": "t", "input": {}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "t")
        self.assertIsNone(parse_action('{"function": {"other": 1}, "input": {}}'))

    def test_openai_style_function_envelope(self):
        # {"function": {"name": ..., "arguments": ...}} is unwrapped (issue #3705)
        action = parse_action('{"function": {"name": "t", "arguments": {"q": 1}}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "t")
        self.assertEqual(action.action_input, {"q": 1})

    def test_openai_style_function_envelope_wrapped(self):
        action = parse_action(
            '{"tool_call": {"function": {"name": "webSearch", "arguments": {"query": "x"}}}}'
        )
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "webSearch")
        self.assertEqual(action.action_input, {"query": "x"})

    def test_openai_style_function_envelope_with_type_key(self):
        # arguments may arrive as a JSON string (OpenAI format) and is kept as-is
        action = parse_action('{"type": "function", "function": {"name": "t", "arguments": "{}"}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_input, "{}")

    def test_openai_style_function_envelope_without_arguments(self):
        action = parse_action('{"function": {"name": "t"}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_input, {})

    def test_openai_style_function_envelope_null_arguments(self):
        # null arguments (and null input) still yield an empty dict input
        action = parse_action('{"function": {"name": "t", "arguments": null, "input": null}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "t")
        self.assertEqual(action.action_input, {})

    def test_openai_style_function_envelope_empty_name(self):
        # an empty envelope name is not a usable tool name
        self.assertIsNone(parse_action('{"function": {"name": "", "arguments": {}}}'))

    def test_explicit_name_key_takes_precedence_over_envelope(self):
        # an explicit canonical name key wins over a nested function envelope
        action = parse_action(
            '{"action": "explicit", "action_input": {"a": 1}, '
            '"function": {"name": "nested", "arguments": {}}}'
        )
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "explicit")
        self.assertEqual(action.action_input, {"a": 1})

    def test_wrapper_keys_are_case_insensitive(self):
        action = parse_action('{"Tool_call": {"action": "webSearch", "action_input": {"q": 1}}}')
        self.assertIsNotNone(action)
        self.assertEqual(action.action_name, "webSearch")
        self.assertEqual(action.action_input, {"q": 1})


class TestReActStreamParsing(unittest.TestCase):
    def test_action_prefix_yields_action(self):
        results = _parse(
            'Thought: let me search\nAction: {"action": "webSearch", "action_input": {"q": 1}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_name, "webSearch")

    def test_tool_call_wrapper_yields_action(self):
        # Issue #3699: previously the wrapper JSON was yielded as thought text
        # and the round ended silently without invoking the tool.
        raw = (
            '{"tool_call": {"thought": "获取。", "action": "webSearch", '
            '"action_input": {"input": "x"}}}'
        )
        results = _parse(raw)
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_name, "webSearch")
        failed = [r for r in results if isinstance(r, ReactChunk) and r.parse_failed]
        self.assertEqual(failed, [])

    def test_flat_action_json_without_prefix_still_works(self):
        results = _parse('{"action": "webSearch", "action_input": {"q": 1}}')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(len(actions), 1)

    def test_action_input_free_text_flags_parse_failure(self):
        # Issue #3699 (2nd scenario): "Action_input: {...}" written as free
        # text inside the thought instead of a properly formatted action line.
        results = _parse('Thought: I need to search\nAction_input: {"input": "x"}')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(actions, [])
        failed = [r for r in results if isinstance(r, ReactChunk) and r.parse_failed]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].content, '{"input": "x"}')

    def test_json_after_final_answer_is_not_an_action(self):
        results = _parse('FinalAnswer: {"action": "webSearch", "action_input": {"q": 1}}')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(actions, [])
        chunks = [r for r in results if isinstance(r, ReactChunk)]
        self.assertTrue(all(c.state == ReactState.ANSWER for c in chunks))
        self.assertTrue(all(not c.parse_failed for c in chunks))

    def test_thought_after_final_answer_cannot_trigger_action(self):
        # the final answer is terminal: a later "Thought:" with an
        # action-looking JSON blob must stay answer text, never a tool call
        results = _parse(
            'FinalAnswer: done\nThought: {"action": "webSearch", "action_input": {"q": 1}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(actions, [])
        chunks = [r for r in results if isinstance(r, ReactChunk)]
        self.assertTrue(all(c.state == ReactState.ANSWER for c in chunks))
        self.assertTrue(all(not c.parse_failed for c in chunks))

    def test_truncated_json_at_stream_end_flags_parse_failure(self):
        results = _parse('Action: {"action": "webSearch", "action_input": {"q": 1')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(actions, [])
        failed = [r for r in results if isinstance(r, ReactChunk) and r.parse_failed]
        self.assertEqual(len(failed), 1)

    def test_adjacent_json_roots_in_same_chunk(self):
        # issue #3705: the first blob used to be dropped when a second
        # JSON root started immediately after the first closed
        results = _parse('{"action": "first", "action_input": {}}{"action": "second", "action_input": {}}')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual([a.action_name for a in actions], ["first", "second"])

    def test_adjacent_json_roots_across_chunks(self):
        results = _parse(
            '{"action": "first", "action_input": {}}',
            '{"action": "second", "action_input": {}}',
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual([a.action_name for a in actions], ["first", "second"])

    def test_adjacent_non_action_blobs_are_both_flagged(self):
        results = _parse('{"foo": 1}{"bar": 2}')
        self.assertEqual(
            [r for r in results if isinstance(r, AgentScratchpadUnit.Action)], []
        )
        failed = [r for r in results if isinstance(r, ReactChunk) and r.parse_failed]
        self.assertEqual(len(failed), 2)

    def test_think_tags_are_stripped(self):
        # The tags are built via chr() to keep this test file free of raw tag
        # literals (see the constants in output_parser.cot_output_parser).
        open_tag = chr(60) + "think" + chr(62)
        close_tag = chr(60) + "/think" + chr(62)
        results = _parse(
            open_tag + "inner" + close_tag + 'Action: {"action": "t", "action_input": {}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_name, "t")
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        self.assertNotIn(open_tag, text)
        self.assertNotIn(close_tag, text)

    def test_think_tags_split_across_chunks(self):
        # issue #3705: tags split across stream chunks used to leak as text
        open_tag = chr(60) + "think" + chr(62)
        close_tag = chr(60) + "/think" + chr(62)
        results = _parse(
            "pre" + open_tag[:4],
            open_tag[4:] + "inner" + close_tag[:5],
            close_tag[5:] + "post",
        )
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        self.assertEqual(text, "prepost")

    def test_closing_think_tag_split_across_chunks(self):
        open_tag = chr(60) + "think" + chr(62)
        close_tag = chr(60) + "/think" + chr(62)
        results = _parse("a" + open_tag + "x" + close_tag[:4], close_tag[4:] + "b")
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        self.assertEqual(text, "ab")

    def test_trailing_partial_tag_flushed_at_stream_end(self):
        # a chunk tail that looks like the start of a tag but never completes
        # must be flushed as content at stream end, not lost
        close_tag = chr(60) + "/think" + chr(62)
        results = _parse("hello" + close_tag[:6])
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        self.assertEqual(text, "hello" + close_tag[:6])

    def test_unclosed_think_at_stream_end_drops_content(self):
        # pre-existing policy: an unclosed think block is discarded
        open_tag = chr(60) + "think" + chr(62)
        results = _parse("keep" + open_tag[:1], open_tag[1:] + "secret")
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        self.assertNotIn("secret", text)

    def test_parse_failed_defaults_to_false(self):
        self.assertFalse(ReactChunk(ReactState.THINKING, "x").parse_failed)


if __name__ == "__main__":
    unittest.main()
