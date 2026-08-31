"""Regression tests for azure_openai fixes (v0.0.68).

Covers:
- B1: stream_options gated by effective Azure api-version
- P0: preflight guard for Responses-routed models on legacy endpoints
- B2: client-side stop enforcement on the Responses route (blocking +
      streaming cross-chunk), never touching tool-call arguments
- B4: real usage from terminal events; fallback estimation
- B4+: terminal status semantics (incomplete -> length; failed -> error)
- B5: synthetic reasoning blocks always closed, in BOTH stream handlers
- B3: defensive image token estimation (remote URLs, malformed payloads)
- Audit: tool_calls accounted in _num_tokens_from_messages

Think-tag literals are constructed via chr() so this source file can be
safely produced by automated pipelines.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

LT, SL = chr(60), chr(62)
THINK_OPEN = LT + "think" + SL  # synthetic open tag
THINK_CLOSE = LT + "/think" + SL  # synthetic close tag

from dify_plugin.entities.model.llm import LLMResult, LLMUsage
from dify_plugin.entities.model.message import AssistantPromptMessage, UserPromptMessage
from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from dify_plugin.errors.model import InvokeBadRequestError

import models.llm.llm as llm_module
from models.llm.llm import AzureOpenAILargeLanguageModel


def make_llm() -> AzureOpenAILargeLanguageModel:
    return object.__new__(AzureOpenAILargeLanguageModel)


def fake_usage(prompt_tokens: int = 0, completion_tokens: int = 0) -> LLMUsage:
    """Real LLMUsage instance (pydantic validates chunks strictly)."""
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        prompt_unit_price=0,
        prompt_price_unit=0,
        prompt_price=0,
        completion_tokens=completion_tokens,
        completion_unit_price=0,
        completion_price_unit=0,
        completion_price=0,
        total_tokens=prompt_tokens + completion_tokens,
        total_price=0,
        currency="USD",
        latency=0,
    )


def mock_calc(llm):
    """Mock _calc_response_usage preserving token numbers through pydantic."""
    llm._calc_response_usage = MagicMock(
        side_effect=lambda model, creds, pt, ct: fake_usage(pt, ct)
    )


V1_BASE = "https://example.openai.azure.com/openai/v1"
LEGACY_BASE = "https://example.openai.azure.com"


def resp_event(event_type: str, **kwargs):
    return SimpleNamespace(type=event_type, **kwargs)


def text_delta(text: str, item_id: str = "item-1"):
    return resp_event("response.output_text.delta", delta=text, item_id=item_id)


def reason_delta(text: str, item_id: str = "item-r"):
    return resp_event("response.reasoning_summary_text.delta", delta=text, item_id=item_id)


def completed_event(input_tokens: int, output_tokens: int):
    return resp_event(
        "response.completed",
        response=SimpleNamespace(
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        ),
    )


class TestStreamOptionsGate(unittest.TestCase):
    """B1: stream_options only when the endpoint supports it."""

    def setUp(self):
        self.llm = make_llm()

    def test_v1_endpoint_supported(self):
        self.assertTrue(self.llm._supports_stream_options({"openai_api_base": V1_BASE}))

    def test_dated_version_below_threshold_unsupported(self):
        creds = {"openai_api_base": LEGACY_BASE, "openai_api_version": "2024-07-01-preview"}
        self.assertFalse(self.llm._supports_stream_options(creds))

    def test_dated_version_at_threshold_supported(self):
        creds = {"openai_api_base": LEGACY_BASE, "openai_api_version": "2024-08-01-preview"}
        self.assertTrue(self.llm._supports_stream_options(creds))

    def test_blank_version_falls_back_to_modern_default_and_is_supported(self):
        # Since 0.0.69 the fallback default is 2025-04-01-preview, which
        # supports stream_options; explicitly old versions stay unsupported.
        creds = {"openai_api_base": LEGACY_BASE}
        self.assertTrue(self.llm._supports_stream_options(creds))
        creds_old = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2024-02-15-preview",
        }
        self.assertFalse(self.llm._supports_stream_options(creds_old))

    def test_chat_generate_includes_stream_options_when_supported(self):
        self.llm._get_base_model_name = MagicMock(return_value="gpt-4o")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock()
        self.llm._create_client = MagicMock(return_value=mock_client)
        self.llm._handle_chat_generate_stream_response = MagicMock(
            return_value=iter(())
        )
        self.llm._clear_illegal_prompt_messages = MagicMock(
            side_effect=lambda _, msgs: msgs
        )
        with unittest.mock.patch.object(
            llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
        ):
            list(
                self.llm._chat_generate(
                    model="deploy",
                    credentials={
                        "base_model_name": "gpt-4o",
                        "openai_api_base": V1_BASE,
                    },
                    prompt_messages=[UserPromptMessage(content="hi")],
                    model_parameters={},
                    stream=True,
                )
            )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["stream_options"], {"include_usage": True})

    def test_chat_generate_omits_stream_options_on_old_versions(self):
        self.llm._get_base_model_name = MagicMock(return_value="gpt-4o")
        self.llm._create_client = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock()
        self.llm._create_client.return_value = mock_client
        self.llm._handle_chat_generate_stream_response = MagicMock(return_value=iter(()))
        self.llm._clear_illegal_prompt_messages = MagicMock(side_effect=lambda _, msgs: msgs)
        with unittest.mock.patch.object(
            llm_module, "apply_dify_metadata_if_enabled", lambda *a, **k: None
        ):
            list(
                self.llm._chat_generate(
                    model="deploy",
                    credentials={
                        "base_model_name": "gpt-4o",
                        "openai_api_base": LEGACY_BASE,
                        "openai_api_version": "2024-02-15-preview",
                    },
                    prompt_messages=[UserPromptMessage(content="hi")],
                    model_parameters={},
                    stream=True,
                )
            )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertNotIn("stream_options", kwargs)


class TestResponsesVersionGuard(unittest.TestCase):
    """P0: fail fast when the endpoint cannot serve the Responses API."""

    def setUp(self):
        self.llm = make_llm()

    def _invoke(self, credentials):
        self.llm._create_client = MagicMock()
        self.llm._get_base_model_name = MagicMock(return_value="gpt-5")
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=1)
        self.llm._create_client.return_value.responses.create.return_value = SimpleNamespace(
            output=[], usage=None, id="resp-1"
        )
        try:
            self.llm._chat_generate_with_responses(
                model="deploy",
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={},
                stream=False,
            )
        except ValueError as ex:
            return str(ex)
        return None

    def test_explicit_pre_responses_version_raises_actionable_error(self):
        message = self._invoke(
            {
                "base_model_name": "gpt-5",
                "openai_api_base": LEGACY_BASE,
                "openai_api_version": "2024-02-15-preview",
            }
        )
        self.assertIsNotNone(message)
        self.assertIn("/openai/v1", message)
        self.assertIn("2025-03-01-preview", message)
        self.assertIn("2024-02-15-preview", message)

    def test_blank_version_uses_modern_default_and_passes_guard(self):
        # Since 0.0.69 the fallback default satisfies the Responses gate.
        result = self._invoke({"base_model_name": "gpt-5", "openai_api_base": LEGACY_BASE})
        self.assertIsNone(result)

    def test_legacy_newer_preview_passes_guard(self):
        result = self._invoke(
            {
                "base_model_name": "gpt-5",
                "openai_api_base": LEGACY_BASE,
                "openai_api_version": "2025-03-01-preview",
            }
        )
        self.assertIsNone(result)

    def test_v1_passes_guard(self):
        result = self._invoke({"base_model_name": "gpt-5", "openai_api_base": V1_BASE})
        self.assertIsNone(result)


class TestResponsesStopEnforcement(unittest.TestCase):
    """B2: stop enforced client-side, output text only."""

    def setUp(self):
        self.llm = make_llm()

    def test_blocking_stop_truncates_message_text(self):
        message_item = SimpleNamespace(
            type="message", content=[SimpleNamespace(type="output_text", text="hello SECRET world")]
        )
        response = SimpleNamespace(output=[message_item], usage=None, id="resp-1")
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=1)
        result = self.llm._handle_responses_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=response,
            prompt_messages=[UserPromptMessage(content="hi")],
            stop=["SECRET"],
        )
        self.assertEqual(result.message.content, "hello ")

    def test_blocking_stop_never_truncates_inside_reasoning(self):
        reasoning_item = SimpleNamespace(
            type="reasoning", summary=[SimpleNamespace(text="SECRET appears in reasoning")]
        )
        message_item = SimpleNamespace(
            type="message", content=[SimpleNamespace(type="output_text", text="plain answer")]
        )
        response = SimpleNamespace(output=[reasoning_item, message_item], usage=None, id="resp-1")
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=1)
        result = self.llm._handle_responses_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=response,
            prompt_messages=[UserPromptMessage(content="hi")],
            stop=["SECRET"],
        )
        # Reasoning wrapper survives; only output text is cut.
        self.assertIn("SECRET appears in reasoning", result.message.content)
        self.assertIn(THINK_OPEN, result.message.content)
        self.assertIn(THINK_CLOSE, result.message.content)
        self.assertIn("plain answer", result.message.content)
        self.assertNotIn("SECRET plain", result.message.content)

    def _collect_stream(self, events, stop=None, tools=None):
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=7)
        gen = self.llm._handle_responses_stream_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=iter(events),
            prompt_messages=[UserPromptMessage(content="hi")],
            tools=tools,
            stop=stop,
        )
        return list(gen)

    @staticmethod
    def _concat(chunks) -> str:
        return "".join(c.delta.message.content or "" for c in chunks)

    def test_streaming_stop_split_across_chunks(self):
        events = [text_delta("say STOP"), text_delta("NOW please"), completed_event(10, 20)]
        chunks = self._collect_stream(events, stop=["STOPNOW"])
        combined = self._concat(chunks)
        self.assertNotIn("STOPNOW", combined)
        self.assertEqual(combined, "say ")
        final = chunks[-1]
        self.assertEqual(final.delta.finish_reason, "stop")
        self.assertIsNotNone(final.delta.usage)

    def test_streaming_tool_call_arguments_ignore_stop(self):
        call_item = SimpleNamespace(type="function_call", name="search", call_id="call-1")
        events = [
            resp_event("response.output_item.added", item=call_item),
            resp_event(
                "response.function_call_arguments.delta", delta='{"q": "SECRET"}', item_id="call-1"
            ),
            resp_event(
                "response.function_call_arguments.done",
                arguments='{"q": "SECRET"}',
                item_id="call-1",
            ),
            resp_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="function_call",
                    name="search",
                    call_id="call-1",
                    arguments='{"q": "SECRET"}',
                ),
            ),
            completed_event(10, 20),
        ]
        chunks = self._collect_stream(events, stop=["SECRET"])
        tool_chunks = [c for c in chunks if c.delta.message.tool_calls]
        self.assertEqual(len(tool_chunks), 1)
        self.assertEqual(
            tool_chunks[0].delta.message.tool_calls[0].function.arguments, '{"q": "SECRET"}'
        )


class TestResponsesUsageAndStatus(unittest.TestCase):
    """B4 + terminal status semantics."""

    def setUp(self):
        self.llm = make_llm()

    def _collect(self, events):
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=3)
        gen = self.llm._handle_responses_stream_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=iter(events),
            prompt_messages=[UserPromptMessage(content="hi")],
        )
        return list(gen)

    def test_real_usage_preferred_over_estimation(self):
        chunks = self._collect([text_delta("ok"), completed_event(123, 45)])
        final = chunks[-1]
        self.assertEqual(final.delta.usage.prompt_tokens, 123)
        self.assertEqual(final.delta.usage.completion_tokens, 45)

    def test_estimation_fallback_without_terminal_usage(self):
        chunks = self._collect([text_delta("hello")])
        final = chunks[-1]
        usage = final.delta.usage
        self.assertIsNotNone(usage)
        self.assertGreater(usage.completion_tokens, 0)

    def test_incomplete_maps_to_length_finish_reason(self):
        incomplete = resp_event(
            "response.incomplete",
            response=SimpleNamespace(
                usage=SimpleNamespace(input_tokens=5, output_tokens=6),
                incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            ),
        )
        chunks = self._collect([text_delta("partial"), incomplete])
        self.assertEqual(chunks[-1].delta.finish_reason, "length")

    def test_failed_terminal_raises(self):
        failed = resp_event(
            "response.failed",
            response=SimpleNamespace(error=SimpleNamespace(message="content filter triggered")),
        )
        with self.assertRaises(InvokeBadRequestError) as ctx:
            self._collect([failed])
        self.assertIn("content filter", str(ctx.exception))


class TestThinkClosureResponsesStream(unittest.TestCase):
    """B5 (Responses): reasoning blocks always closed."""

    def setUp(self):
        self.llm = make_llm()

    def _collect(self, events):
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=3)
        gen = self.llm._handle_responses_stream_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=iter(events),
            prompt_messages=[UserPromptMessage(content="hi")],
        )
        return list(gen)

    @staticmethod
    def _concat(chunks) -> str:
        return "".join(c.delta.message.content or "" for c in chunks)

    def test_reasoning_only_stream_closes_tag(self):
        chunks = self._collect([reason_delta("deep thought"), completed_event(1, 2)])
        combined = self._concat(chunks)
        self.assertIn(THINK_OPEN, combined)
        self.assertIn(THINK_CLOSE, combined)
        # Closing tag is its own emitted chunk, not just internal state.
        closing_chunks = [c for c in chunks if c.delta.message.content == "\n" + THINK_CLOSE]
        self.assertEqual(len(closing_chunks), 1)

    def test_closure_emitted_before_tool_call_output(self):
        call_item = SimpleNamespace(type="function_call", name="lookup", call_id="c9")
        events = [
            reason_delta("ponder"),
            resp_event("response.output_item.added", item=call_item),
            resp_event(
                "response.output_item.done",
                item=SimpleNamespace(
                    type="function_call", name="lookup", call_id="c9", arguments="{}"
                ),
            ),
            completed_event(1, 2),
        ]
        chunks = self._collect(events)
        contents = [c.delta.message.content for c in chunks]
        close_positions = [i for i, c in enumerate(contents) if c == "\n" + THINK_CLOSE]
        tool_positions = [i for i, c in enumerate(chunks) if c.delta.message.tool_calls]
        self.assertEqual(len(close_positions), 1)
        self.assertEqual(len(tool_positions), 1)
        self.assertLess(close_positions[0], tool_positions[0])


class TestThinkClosureChatCompletionsStream(unittest.TestCase):
    """B5 (Chat Completions): same closure guarantee."""

    def _chunks(self):
        reasoning_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None, reasoning_content="hmm", tool_calls=None),
                    finish_reason=None,
                )
            ],
            usage=None,
            model="gpt-4o",
            system_fingerprint="fp1",
        )
        usage_chunk = SimpleNamespace(
            choices=[], usage=None, model="gpt-4o", system_fingerprint="fp1"
        )
        return reasoning_chunk, usage_chunk

    def test_closure_after_reasoning_only_stream(self):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=2)
        reasoning_chunk, usage_chunk = self._chunks()

        def stream():
            yield reasoning_chunk
            u = SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                model="gpt-4o",
                system_fingerprint="fp1",
            )
            yield u

        out = list(
            llm._handle_chat_generate_stream_response(
                model="gpt-4o",
                credentials={"base_model_name": "gpt-4o"},
                response=stream(),
                prompt_messages=[UserPromptMessage(content="hi")],
            )
        )
        contents = [c.delta.message.content for c in out]
        self.assertIn("\n" + THINK_CLOSE, contents)
        # Closure precedes the terminal usage chunk.
        self.assertEqual(contents[-1], "")
        self.assertIsNotNone(out[-1].delta.usage)


class TestImageTokenEstimation(unittest.TestCase):
    """B3: never crash on remote/malformed images; estimate conservatively."""

    def setUp(self):
        self.llm = make_llm()

    def _count(self, details, base_model="gpt-4o"):
        return self.llm._num_tokens_from_images(base_model_name=base_model, image_details=details)

    def test_remote_url_image_does_not_crash(self):
        total = self._count([{"url": "https://example.com/cat.png", "detail": "high"}])
        self.assertGreater(total, 0)

    def test_malformed_data_uri_does_not_crash(self):
        total = self._count([{"url": "data:image/png;base64,", "detail": "high"}])
        self.assertGreater(total, 0)

    def test_missing_detail_key_does_not_crash(self):
        import base64 as b64mod
        import io as iomod

        from PIL import Image as PILImage

        img = PILImage.new("RGB", (64, 64), color=(1, 2, 3))
        buf = iomod.BytesIO()
        img.save(buf, format="PNG")
        encoded = b64mod.b64encode(buf.getvalue()).decode()
        data_uri = f"data:image/png;base64,{encoded}"
        total = self._count([{"url": data_uri}])
        self.assertGreater(total, 0)

    def test_low_detail_data_uri_fixed_cost(self):
        import base64 as b64mod
        import io as iomod

        from PIL import Image as PILImage

        img = PILImage.new("RGB", (3000, 3000), color=(9, 9, 9))
        buf = iomod.BytesIO()
        img.save(buf, format="PNG")
        encoded = b64mod.b64encode(buf.getvalue()).decode()
        data_uri = f"data:image/png;base64,{encoded}"
        total = self._count([{"url": data_uri, "detail": "low"}])
        self.assertEqual(total, 85)


class TestToolCallsTokenAccounting(unittest.TestCase):
    """Audit: tool_calls must be counted despite list flattening."""

    def test_assistant_tool_calls_increase_count(self):
        llm = make_llm()
        creds = {"base_model_name": "gpt-4o"}
        tool_call = AssistantPromptMessage.ToolCall(
            id="call-1",
            type="function",
            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                name="get_weather", arguments='{"city": "Lisbon"}'
            ),
        )
        with_tools = AssistantPromptMessage(content="", tool_calls=[tool_call])
        without_tools = AssistantPromptMessage(content="")
        n_with = llm._num_tokens_from_messages(creds, [with_tools])
        n_without = llm._num_tokens_from_messages(creds, [without_tools])
        self.assertGreater(n_with, n_without)
        # The delta must reflect the serialized call, not an empty string.
        self.assertGreaterEqual(n_with - n_without, 15)


class TestStopLiteralSemantics(unittest.TestCase):
    """Round-2: stop matching is literal, consistent blocking vs streaming."""

    def setUp(self):
        self.llm = make_llm()

    def test_blocking_regex_metacharacters_are_literal(self):
        message_item = SimpleNamespace(
            type="message",
            content=[SimpleNamespace(type="output_text", text="a.b continues")],
        )
        response = SimpleNamespace(output=[message_item], usage=None, id="r")
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=1)
        result = self.llm._handle_responses_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=response,
            prompt_messages=[UserPromptMessage(content="hi")],
            stop=["."],
        )
        self.assertEqual(result.message.content, "a")

    def test_blocking_bracket_stop_does_not_raise(self):
        message_item = SimpleNamespace(
            type="message",
            content=[SimpleNamespace(type="output_text", text="arr[0] tail")],
        )
        response = SimpleNamespace(output=[message_item], usage=None, id="r")
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=1)
        result = self.llm._handle_responses_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=response,
            prompt_messages=[UserPromptMessage(content="hi")],
            stop=["["],
        )
        self.assertEqual(result.message.content, "arr")


class TestStreamOrdering(unittest.TestCase):
    """Round-2: held-back text flushes before tool output."""

    def _collect(self, events, stop=None):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=3)
        gen = llm._handle_responses_stream_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=iter(events),
            prompt_messages=[UserPromptMessage(content="hi")],
            stop=stop,
        )
        return list(gen)

    def test_held_back_text_precedes_tool_call(self):
        # "ok" is shorter than any holdback for an 8-char stop sequence.
        call_item_done = SimpleNamespace(
            type="function_call",
            name="lookup",
            call_id="c1",
            arguments="{}",
        )
        events = [
            resp_event("response.output_text.delta", delta="ok", item_id="t"),
            resp_event("response.output_item.done", item=call_item_done),
            completed_event(1, 2),
        ]
        chunks = self._collect(events, stop=["SHOULDSTOP"])
        kinds = []
        for c in chunks:
            if c.delta.message.tool_calls:
                kinds.append("tool")
            elif c.delta.message.content == "ok":
                kinds.append("text")
        self.assertIn("text", kinds)
        self.assertIn("tool", kinds)
        self.assertLess(kinds.index("text"), kinds.index("tool"))

    def test_reasoning_to_text_emits_standalone_closure_first(self):
        events = [
            reason_delta("thinking"),
            resp_event("response.output_text.delta", delta="answer", item_id="t"),
            completed_event(1, 2),
        ]
        chunks = self._collect(events)
        contents = [c.delta.message.content or "" for c in chunks]
        close_idx = next(
            i for i, c in enumerate(contents) if c == "\n" + THINK_CLOSE
        )
        text_idx = next(i for i, c in enumerate(contents) if c == "answer")
        self.assertLess(close_idx, text_idx)

    def test_fallback_estimation_includes_streamed_tool_calls(self):
        llm = make_llm()
        mock_calc(llm)
        num_mock = MagicMock(return_value=5)
        llm._num_tokens_from_messages = num_mock
        call_item_added = SimpleNamespace(
            type="function_call", name="lookup", call_id="c2"
        )
        call_item_done = SimpleNamespace(
            type="function_call",
            name="lookup",
            call_id="c2",
            arguments='{"x": 1}',
        )
        events = [
            resp_event("response.output_item.added", item=call_item_added),
            resp_event(
                "response.function_call_arguments.done",
                arguments='{"x": 1}',
                item_id="c2",
            ),
            resp_event("response.output_item.done", item=call_item_done),
            # No completed event carrying usage -> estimation path.
        ]
        list(llm._handle_responses_stream_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=iter(events),
            prompt_messages=[UserPromptMessage(content="hi")],
        ))
        est_msg = num_mock.call_args_list[-1].args[1][0]
        self.assertTrue(est_msg.tool_calls)
        self.assertEqual(est_msg.tool_calls[0].function.name, "lookup")


class TestChatStreamClosureTransitions(unittest.TestCase):
    """Round-2: chat closure before visible text and before tool calls."""

    def _run(self, deltas):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=2)

        def stream():
            for d, finish in deltas:
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(delta=d, finish_reason=finish)
                    ],
                    usage=None,
                    model="gpt-4o",
                    system_fingerprint="fp",
                )

        return list(
            llm._handle_chat_generate_stream_response(
                model="gpt-4o",
                credentials={"base_model_name": "gpt-4o"},
                response=stream(),
                prompt_messages=[UserPromptMessage(content="hi")],
            )
        )

    @staticmethod
    def _d(content=None, rc=None, tools=None):
        return SimpleNamespace(
            content=content, reasoning_content=rc, tool_calls=tools
        )

    def test_reasoning_to_text_closes_as_own_chunk(self):
        out = self._run([
            (self._d(rc="deep"), None),
            (self._d(content="visible"), None),
        ])
        contents = [c.delta.message.content for c in out]
        close_idx = next(
            i for i, c in enumerate(contents) if c == "\n" + THINK_CLOSE
        )
        text_idx = next(i for i, c in enumerate(contents) if c == "visible")
        self.assertLess(close_idx, text_idx)
        # The closure must be standalone - not prefixed onto the text chunk.
        self.assertNotIn(THINK_CLOSE, contents[text_idx])

    def test_reasoning_to_tool_call_closes_before_tools(self):
        delta_tool = ChoiceDeltaToolCall(
            index=0,
            id="call-9",
            type="function",
            function=ChoiceDeltaToolCallFunction(name="f", arguments="{}"),
        )
        out = self._run([
            (self._d(rc="hmm"), None),
            (self._d(tools=[delta_tool]), None),
            (self._d(), "stop"),
        ])
        contents = [c.delta.message.content for c in out]
        close_idx = next(
            i for i, c in enumerate(contents) if c == "\n" + THINK_CLOSE
        )
        tool_idx = next(
            i for i, c in enumerate(out) if c.delta.message.tool_calls
        )
        self.assertLess(close_idx, tool_idx)


class TestBlockingChatToolOnlyResponse(unittest.TestCase):
    """Round-2: content=None with tool calls must not crash."""

    def test_tool_only_message_content_none(self):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=3)
        from openai.types.chat.chat_completion_message_function_tool_call import (
            Function as MessageFunction,
        )

        sdk_tool_call = ChatCompletionMessageToolCall(
            id="c1",
            type="function",
            function=MessageFunction(name="f", arguments="{}"),
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        reasoning_content=None,
                        model_extra=None,
                        tool_calls=[sdk_tool_call],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            model="gpt-4o",
            system_fingerprint="fp",
        )
        result = llm._handle_chat_generate_response(
            model="gpt-4o",
            credentials={"base_model_name": "gpt-4o"},
            response=response,
            prompt_messages=[UserPromptMessage(content="hi")],
        )
        self.assertEqual(result.message.content, "")
        self.assertEqual(len(result.message.tool_calls), 1)


class TestCredentialRobustness(unittest.TestCase):
    """Round-2: None/malformed credential values fail closed, not loud."""

    def setUp(self):
        self.llm = make_llm()

    def test_none_api_base_falls_back_to_default_version_gate(self):
        # Missing base URL behaves like a dated endpoint evaluated against
        # the fallback default (modern since 0.0.69).
        creds = {"openai_api_base": None}
        self.assertTrue(self.llm._supports_stream_options(creds))

    def test_malformed_version_fails_closed(self):
        creds = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2025-3-1-preview",
        }
        self.assertFalse(self.llm._supports_stream_options(creds))

    def test_guard_reports_invalid_version_actionably(self):
        self.llm._create_client = MagicMock()
        self.llm._get_base_model_name = MagicMock(return_value="gpt-5")
        mock_calc(self.llm)
        self.llm._num_tokens_from_messages = MagicMock(return_value=1)
        self.llm._create_client.return_value.responses.create.return_value = (
            SimpleNamespace(output=[], usage=None, id="resp-1")
        )
        with self.assertRaises(ValueError) as ctx:
            self.llm._chat_generate_with_responses(
                model="deploy",
                credentials={
                    "base_model_name": "gpt-5",
                    "openai_api_base": LEGACY_BASE,
                    "openai_api_version": "bogus",
                },
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={},
                stream=False,
            )
        self.assertIn("bogus", str(ctx.exception))


class TestErrorTerminalEvent(unittest.TestCase):
    """Round-2: top-level error events raise instead of pretending success."""

    def test_error_event_raises(self):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=1)
        gen = llm._handle_responses_stream_response(
            model="gpt-5",
            credentials={"base_model_name": "gpt-5"},
            response=iter([resp_event("error", message="boom")]),
            prompt_messages=[UserPromptMessage(content="hi")],
        )
        with self.assertRaises(InvokeBadRequestError):
            list(gen)


class TestModelExtraNone(unittest.TestCase):
    """Round-3: blocking chat must tolerate model_extra=None."""

    def _response(self, message):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            model="gpt-4o",
            system_fingerprint="fp",
        )

    def _invoke(self, message):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=2)
        return llm._handle_chat_generate_response(
            model="gpt-4o",
            credentials={"base_model_name": "gpt-4o"},
            response=self._response(message),
            prompt_messages=[UserPromptMessage(content="hi")],
        )

    def test_plain_completion_model_extra_none(self):
        message = SimpleNamespace(
            content="hello", reasoning_content=None, model_extra=None, tool_calls=None
        )
        result = self._invoke(message)
        self.assertEqual(result.message.content, "hello")

    def test_reasoning_via_direct_attribute(self):
        message = SimpleNamespace(
            content="answer",
            reasoning_content="why",
            model_extra=None,
            tool_calls=None,
        )
        result = self._invoke(message)
        self.assertIn(THINK_OPEN, result.message.content)
        self.assertIn("why", result.message.content)
        self.assertIn("answer", result.message.content)


class TestO1BlockAsStreamStop(unittest.TestCase):
    """Round-3: the o1 block-as-stream path uses literal stop matching too."""

    def test_literal_stop_on_block_as_stream(self):
        llm = make_llm()
        block_result = LLMResult(
            model="o1",
            prompt_messages=[UserPromptMessage(content="hi")],
            message=AssistantPromptMessage(content="before.MARK after"),
            usage=fake_usage(1, 10),
        )
        out = list(
            llm._handle_chat_block_as_stream_response(
                block_result,
                [UserPromptMessage(content="hi")],
                stop=["."],
            )
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].delta.message.content, "before")


class TestSparseToolCallDelta(unittest.TestCase):
    """Round-3: arguments-only first delta accumulates without asserts."""

    def test_arguments_only_first_delta(self):
        llm = make_llm()
        tool_calls: list = []
        first = ChoiceDeltaToolCall(
            index=0,
            function=ChoiceDeltaToolCallFunction(arguments='{"a"'),
        )
        second = ChoiceDeltaToolCall(
            index=0,
            id="call-x",
            type="function",
            function=ChoiceDeltaToolCallFunction(name="f", arguments="}"),
        )
        llm._update_tool_calls(tool_calls, [first])
        llm._update_tool_calls(tool_calls, [second])
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].id, "call-x")
        self.assertEqual(tool_calls[0].function.name, "f")
        self.assertEqual(tool_calls[0].function.arguments, '{"a"}')


class TestChatMixedReasoningAndTools(unittest.TestCase):
    """Round-3: same-delta reasoning + tool activity stays ordered."""

    def _run(self, deltas):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=2)

        def stream():
            for d, finish in deltas:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=d, finish_reason=finish)],
                    usage=None,
                    model="gpt-4o",
                    system_fingerprint="fp",
                )

        return list(
            llm._handle_chat_generate_stream_response(
                model="gpt-4o",
                credentials={"base_model_name": "gpt-4o"},
                response=stream(),
                prompt_messages=[UserPromptMessage(content="hi")],
            )
        )

    def test_reasoning_plus_tool_in_one_delta(self):
        delta_tool = ChoiceDeltaToolCall(
            index=0,
            id="call-mix",
            type="function",
            function=ChoiceDeltaToolCallFunction(name="f", arguments="{}"),
        )
        mixed_delta = SimpleNamespace(
            content=None,
            reasoning_content="think hard",
            tool_calls=[delta_tool],
        )
        out = self._run([
            (mixed_delta, None),
            (SimpleNamespace(
                content=None, reasoning_content=None, tool_calls=None
            ), "stop"),
        ])
        contents = [c.delta.message.content or "" for c in out]
        reason_idx = next(i for i, c in enumerate(contents) if "think hard" in c)
        close_idx = next(
            i for i, c in enumerate(contents) if c == "\n" + THINK_CLOSE
        )
        tool_idx = next(i for i, c in enumerate(out) if c.delta.message.tool_calls)
        self.assertLess(reason_idx, close_idx)
        self.assertLess(close_idx, tool_idx)
        self.assertFalse(out[reason_idx].delta.message.tool_calls)


class TestVersionValidation(unittest.TestCase):
    """Round-3: newline traps and impossible dates fail closed."""

    def setUp(self):
        self.llm = make_llm()

    def test_trailing_newline_rejected(self):
        creds = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2024-08-01-preview\n",
        }
        self.assertFalse(self.llm._supports_stream_options(creds))

    def test_impossible_calendar_date_rejected(self):
        creds = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2024-99-99-preview",
        }
        self.assertFalse(self.llm._supports_stream_options(creds))

    def test_ga_version_without_suffix_accepted(self):
        creds = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2024-10-21",
        }
        self.assertTrue(self.llm._supports_stream_options(creds))


class TestResponsesInputKeepsAssistantProse(unittest.TestCase):
    """Round-3: assistant text survives alongside its tool calls."""

    def test_prose_and_tool_calls_both_emitted(self):
        llm = make_llm()
        tool_call = AssistantPromptMessage.ToolCall(
            id="c1",
            type="function",
            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                name="f", arguments="{}"
            ),
        )
        messages = [
            AssistantPromptMessage(content="let me check", tool_calls=[tool_call])
        ]
        result = llm._convert_prompt_messages_to_responses_input(messages)
        roles = [m.get("role") for m in result if "role" in m]
        types = [m.get("type") for m in result if "type" in m]
        self.assertIn("assistant", roles)
        self.assertIn("function_call", types)


class TestEmptyEndpointRejected(unittest.TestCase):
    """Round-3: blank base URL fails with a clear message at client build."""

    def test_empty_base_url_raises_value_error(self):
        from models.common import _CommonAzureOpenAI as C

        with self.assertRaises(ValueError) as ctx:
            C._to_credential_kwargs({"openai_api_base": "", "openai_api_key": "k"})
        self.assertIn("Base URL is required", str(ctx.exception))


class TestPlainTextStreamLifecycle(unittest.TestCase):
    """Round-4: pieces reset per delta - no UnboundLocalError, no duplication."""

    def _run(self, deltas):
        llm = make_llm()
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=2)

        def stream():
            for d, finish in deltas:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=d, finish_reason=finish)],
                    usage=None,
                    model="gpt-4o",
                    system_fingerprint="fp",
                )

        return list(
            llm._handle_chat_generate_stream_response(
                model="gpt-4o",
                credentials={"base_model_name": "gpt-4o"},
                response=stream(),
                prompt_messages=[UserPromptMessage(content="hi")],
            )
        )

    @staticmethod
    def _d(content=None, rc=None, tools=None):
        return SimpleNamespace(
            content=content, reasoning_content=rc, tool_calls=tools
        )

    def test_plain_text_first_no_crash_and_no_duplication(self):
        out = self._run([
            (self._d(content="A"), None),
            (self._d(content="B"), None),
            (self._d(), "stop"),
        ])
        texts = [c.delta.message.content or "" for c in out if c.delta.message.content]
        # Exactly one chunk carries "A" and one carries "B".
        self.assertEqual(texts.count("A"), 1)
        self.assertEqual(texts.count("B"), 1)
        combined = "".join(texts)
        self.assertIn("AB", combined)
        self.assertNotIn("AABB", combined)

    def test_mixed_reasoning_plus_text_same_delta_keeps_both(self):
        out = self._run([
            (self._d(content="visible", rc="thoughts"), None),
            (self._d(), "stop"),
        ])
        contents = [c.delta.message.content or "" for c in out]
        joined = "".join(contents)
        self.assertIn("thoughts", joined)
        self.assertIn("visible", joined)
        self.assertIn(THINK_OPEN, joined)
        self.assertIn(THINK_CLOSE, joined)

    def test_emitted_tool_ids_never_empty(self):
        delta_tool = ChoiceDeltaToolCall(
            index=0,
            function=ChoiceDeltaToolCallFunction(arguments="{}"),
        )
        id_delta = ChoiceDeltaToolCall(
            index=0,
            id="real-id",
            type="function",
            function=ChoiceDeltaToolCallFunction(name="f", arguments="{}"),
        )
        out = self._run([
            (SimpleNamespace(
                content=None, reasoning_content=None,
                tool_calls=[delta_tool],
            ), None),
            (SimpleNamespace(
                content=None, reasoning_content=None,
                tool_calls=[id_delta],
            ), None),
            (self._d(), "stop"),
        ])
        for chunk in out:
            for tc in chunk.delta.message.tool_calls:
                self.assertTrue(tc.id)


class TestGaBoundaryComparison(unittest.TestCase):
    """Round-4: GA release ON the threshold date satisfies preview minimum."""

    def setUp(self):
        self.llm = make_llm()

    def test_ga_on_threshold_date_passes(self):
        creds = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2024-08-01",
        }
        self.assertTrue(self.llm._supports_stream_options(creds))

    def test_ga_below_threshold_fails(self):
        creds = {
            "openai_api_base": LEGACY_BASE,
            "openai_api_version": "2024-07-15",
        }
        self.assertFalse(self.llm._supports_stream_options(creds))

    def test_responses_ga_boundary(self):
        llm = make_llm()
        llm._create_client = MagicMock()
        llm._get_base_model_name = MagicMock(return_value="gpt-5")
        mock_calc(llm)
        llm._num_tokens_from_messages = MagicMock(return_value=1)
        llm._create_client.return_value.responses.create.return_value = (
            SimpleNamespace(output=[], usage=None, id="r1")
        )
        try:
            llm._chat_generate_with_responses(
                model="deploy",
                credentials={
                    "base_model_name": "gpt-5",
                    "openai_api_base": LEGACY_BASE,
                    "openai_api_version": "2025-03-01",
                },
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={},
                stream=False,
            )
        except ValueError:
            self.fail("GA 2025-03-01 must satisfy the Responses gate")


if __name__ == "__main__":
    unittest.main()
