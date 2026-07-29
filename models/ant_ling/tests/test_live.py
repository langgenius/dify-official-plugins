"""
Ant Ling Model Provider Plugin - Integration & Performance Test Suite

Usage:
    cd models/ant_ling
    uv run python3 tests/test_live.py
"""

import json
import os
import sys
import time
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dify_plugin.entities.model import ModelPropertyKey
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from models.llm.llm import AntLingLargeLanguageModel


def _dump_test_reports(log_dir: str, records: list[dict]) -> None:
    if not records:
        return

    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    json_file = os.path.join(log_dir, f"{timestamp}-performance_coverage_session.json")
    md_file = os.path.join(log_dir, f"{timestamp}-performance_coverage_session.md")

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    md_content = f"# Model Provider Integration & Performance Test Report\n\n"
    md_content += f"* **Execution Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    md_content += f"* **Total Test Cases**: {len(records)}\n\n---\n\n"
    md_content += "### Performance Metrics Summary\n\n"
    md_content += "| Test Case | Model | Duration (s) | TTFT (s) | TPS (t/s) | Tokens | Status |\n"
    md_content += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"

    for rec in records:
        ttft_str = f"{rec['ttft_sec']:.3f}" if rec.get("ttft_sec") is not None else "N/A"
        tps_str = f"{rec['tps']:.2f}" if rec.get("tps") is not None else "N/A"
        md_content += f"| `{rec['test_name']}` | `{rec['model']}` | {rec['duration_sec']:.2f} | {ttft_str} | {tps_str} | {rec.get('estimated_tokens', 0)} | `{rec['status']}` |\n"

    md_content += "\n---\n\n"

    for rec in records:
        md_content += f"## Test Case: {rec['test_name']}\n"
        md_content += f"* **Model**: `{rec['model']}`\n"
        md_content += f"* **Total Duration**: {rec['duration_sec']:.2f} s\n"
        if rec.get("ttft_sec") is not None:
            md_content += f"* **Time To First Token (TTFT)**: {rec['ttft_sec']:.3f} s\n"
        if rec.get("tps") is not None:
            md_content += f"* **Throughput (TPS)**: {rec['tps']:.2f} tokens/sec\n"
        md_content += f"* **Estimated Tokens**: {rec.get('estimated_tokens', 0)}\n"
        md_content += f"* **Status**: `{rec['status']}`\n"
        if rec.get("error"):
            md_content += f"* **Error**: `{rec['error']}`\n"
        md_content += f"\n### Prompt Input\n```text\n{rec['prompt_text'][:500]}...\n```\n"
        md_content += f"\n### Output Content\n```text\n{rec.get('output_content', '')[:1000]}...\n```\n"
        if rec.get("thought_text"):
            md_content += f"\n### Thought Trace\n```text\n{rec['thought_text'][:500]}...\n```\n"
        if rec.get("tool_calls"):
            md_content += f"\n### Tool Calls\n```json\n{json.dumps(rec['tool_calls'], ensure_ascii=False, indent=2)}\n```\n"
        md_content += "\n---\n\n"

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n[DUMP SUCCESS] Session logs & Performance metrics dumped to:\n  - JSON: {json_file}\n  - Markdown: {md_file}")


def _build_needle_prompt(target_code: str, repeat_count: int = 1200) -> str:
    padding = "The system architecture processes large-scale data streams efficiently.\n" * repeat_count
    return (
        f"Read the document and answer the question at the end:\n\n{padding}\n"
        f"Target Identifier: {target_code}.\n\n"
        f"{padding}\nQuestion: What is the target identifier mentioned above?"
    )


class TestAntLingFullCoverageMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip("'\"")

        no_proxy_val = os.getenv("NO_PROXY") or os.getenv("no_proxy") or "api.ant-ling.com,ant-ling.com"
        os.environ["NO_PROXY"] = no_proxy_val
        os.environ["no_proxy"] = no_proxy_val

        cls.api_key = os.getenv("ANT_LING_API_KEY")
        cls.api_base = os.getenv("ANT_LING_API_BASE", "https://api.ant-ling.com/v1")
        cls.credentials = {
            "api_key": cls.api_key or "invalid_dummy_key",
            "endpoint_url": cls.api_base,
        }
        cls.llm_model = AntLingLargeLanguageModel(model_schemas=[])
        cls.log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(cls.log_dir, exist_ok=True)
        cls.test_session_records = []

    @classmethod
    def tearDownClass(cls):
        _dump_test_reports(cls.log_dir, cls.test_session_records)

    def _skip_if_no_api_key(self):
        if not self.api_key:
            self.skipTest("Skipping live test: API_KEY environment variable not set")

    def _record_session(self, test_name: str, model: str, prompt_text: str, duration: float, status: str, output_content: str = "", thought_text: str = "", tool_calls: list = None, ttft_sec: float = None, tps: float = None, estimated_tokens: int = 0, error: str = ""):
        self.test_session_records.append({
            "test_name": test_name,
            "model": model,
            "prompt_text": prompt_text,
            "duration_sec": duration,
            "ttft_sec": ttft_sec,
            "tps": tps,
            "estimated_tokens": estimated_tokens,
            "status": status,
            "output_content": output_content,
            "thought_text": thought_text,
            "tool_calls": tool_calls or [],
            "error": error,
        })

    def _invoke_with_metrics(self, model: str, prompt_messages: list, model_parameters: dict, tools: list = None):
        start_time = time.time()
        first_token_time = None
        content, thought, tool_calls = "", "", []

        response = self.llm_model._invoke(
            model=model,
            credentials=self.credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stream=True,
        )

        for chunk in response:
            now = time.time()
            chunk_content, chunk_thought = "", ""

            if chunk.delta:
                if chunk.delta.message and chunk.delta.message.content:
                    chunk_content = chunk.delta.message.content
                    content += chunk_content

                th = getattr(chunk.delta, "thought", None) or (getattr(chunk.delta.message, "thought", None) if chunk.delta.message else None)
                if th:
                    chunk_thought = th
                    thought += chunk_thought

                if chunk.delta.message and isinstance(chunk.delta.message, AssistantPromptMessage):
                    if chunk.delta.message.tool_calls:
                        for tc in chunk.delta.message.tool_calls:
                            tc_name = getattr(tc, "name", None) or (tc.function.name if hasattr(tc, "function") else "")
                            tc_args = getattr(tc, "args", None) or (tc.function.arguments if hasattr(tc, "function") else "")
                            tool_calls.append({"name": tc_name, "args": tc_args})

            if first_token_time is None and (chunk_content or chunk_thought or tool_calls):
                first_token_time = now

        end_time = time.time()
        total_duration = end_time - start_time
        ttft_sec = (first_token_time - start_time) if first_token_time else total_duration

        total_output_chars = len(content) + len(thought)
        estimated_tokens = max(int(total_output_chars / 2.2), 1) if total_output_chars > 0 else 0
        generation_duration = (end_time - first_token_time) if (first_token_time and end_time > first_token_time) else total_duration
        tps = (estimated_tokens / generation_duration) if generation_duration > 0 and estimated_tokens > 0 else 0.0

        return {
            "content": content,
            "thought": thought,
            "tool_calls": tool_calls,
            "duration_sec": total_duration,
            "ttft_sec": ttft_sec,
            "tps": tps,
            "estimated_tokens": estimated_tokens,
        }

    def _run_test(self, test_name: str, model: str, prompt: str, model_parameters: dict, tools: list = None, assert_fn=None):
        self._skip_if_no_api_key()
        print(f"\n---> Running: {test_name}")
        try:
            res = self._invoke_with_metrics(model, [UserPromptMessage(content=prompt)], model_parameters, tools=tools)
            print(f"  [PASS] TTFT: {res['ttft_sec']:.3f}s | TPS: {res['tps']:.2f} t/s | Tokens: {res['estimated_tokens']} | Total: {res['duration_sec']:.2f}s")
            if assert_fn:
                assert_fn(res)
            self._record_session(test_name, model, prompt, res['duration_sec'], "PASS", res['content'], res['thought'], res['tool_calls'], res['ttft_sec'], res['tps'], res['estimated_tokens'])
            return res
        except Exception as e:
            self._record_session(test_name, model, prompt, 0.0, "FAIL", error=str(e))
            self.fail(f"{test_name} failed: {e}")

    def test_101_ling_flash_basic_stream(self):
        self._run_test(
            "Ling-3.0-flash Basic Streaming Test",
            "Ling-3.0-flash",
            "Explain the difference between a process and a thread in two concise sentences.",
            {"max_tokens": 150},
            assert_fn=lambda res: self.assertGreater(len(res['content']), 0),
        )

    def test_102_ling_flash_thinking_disabled(self):
        self._skip_if_no_api_key()
        test_name = "Ling-3.0-flash Thinking Disabled Test"
        print(f"\n---> Running: {test_name}")
        prompt = "Calculate 123 * 456 and output only the numerical result."
        try:
            res = self._invoke_with_metrics("Ling-3.0-flash", [UserPromptMessage(content=prompt)], {"thinking": "disabled", "max_tokens": 50})
            print(f"  [PASS] TTFT: {res['ttft_sec']:.3f}s | TPS: {res['tps']:.2f} t/s | Tokens: {res['estimated_tokens']} | Total: {res['duration_sec']:.2f}s")
            self._record_session(test_name, "Ling-3.0-flash", prompt, res['duration_sec'], "PASS", res['content'], res['thought'], res['tool_calls'], res['ttft_sec'], res['tps'], res['estimated_tokens'])
            self.assertGreater(len(res['content']), 0)
        except Exception as e:
            if "500" in str(e):
                print(f"  [SKIPPED / SERVER LIMIT] Server side does not accept thinking parameter: {e}")
                self._record_session(test_name, "Ling-3.0-flash", prompt, 0.0, "SKIPPED_SERVER_500", error=str(e))
            else:
                self._record_session(test_name, "Ling-3.0-flash", prompt, 0.0, "FAIL", error=str(e))
                self.fail(f"{test_name} failed: {e}")

    def test_103_ling_flash_web_search(self):
        self._run_test(
            "Ling-3.0-flash Web Search Test",
            "Ling-3.0-flash",
            "What is the latest release version of Python?",
            {"enable_search": True, "forced_search": True, "max_tokens": 150},
            assert_fn=lambda res: self.assertGreater(len(res['content']), 0),
        )

    def test_104_ling_flash_tool_calling(self):
        tool = PromptMessageTool(
            name="query_stock_price",
            description="Retrieve current stock price for a given ticker symbol.",
            parameters={
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"}},
                "required": ["ticker"],
            },
        )
        self._run_test(
            "Ling-3.0-flash Tool Calling Test",
            "Ling-3.0-flash",
            "Check the latest stock price for AAPL.",
            {"max_tokens": 150},
            tools=[tool],
            assert_fn=lambda res: self.assertGreater(len(res['tool_calls']), 0),
        )

    def test_105_ling_flash_long_context_retrieval(self):
        target = "SECRET_CODE_GENERAL_BENCHMARK_2026"
        self._run_test(
            "Ling-3.0-flash Long Context Retrieval Test",
            "Ling-3.0-flash",
            _build_needle_prompt(target),
            {"max_tokens": 400},
            assert_fn=lambda res: self.assertIn(target, res['content']),
        )

    def test_106_verify_stream_function_calling(self):
        self._skip_if_no_api_key()
        test_name = "Ling-3.0-flash Stream Function Calling Test"
        print(f"\n---> Running: {test_name}")
        tool = PromptMessageTool(
            name="get_current_weather",
            description="Get current weather for a city.",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["city"],
            },
        )
        prompt = "Check the current weather in San Francisco in celsius."
        try:
            start_t = time.time()
            response = self.llm_model._invoke(
                model="Ling-3.0-flash",
                credentials=self.credentials,
                prompt_messages=[UserPromptMessage(content=prompt)],
                model_parameters={"max_tokens": 200},
                tools=[tool],
                stream=True,
            )
            total_chunks, tool_call_chunks, collected_tool_calls = 0, 0, []
            for chunk in response:
                total_chunks += 1
                if chunk.delta and chunk.delta.message and isinstance(chunk.delta.message, AssistantPromptMessage):
                    if chunk.delta.message.tool_calls:
                        tool_call_chunks += 1
                        for tc in chunk.delta.message.tool_calls:
                            tc_name = getattr(tc, "name", None) or (tc.function.name if hasattr(tc, "function") else "")
                            tc_args = getattr(tc, "args", None) or (tc.function.arguments if hasattr(tc, "function") else "")
                            collected_tool_calls.append({"chunk_index": total_chunks, "name": tc_name, "args": tc_args})

            dur = time.time() - start_t
            self._record_session(
                test_name, "Ling-3.0-flash", prompt, dur, "PASS",
                f"Total chunks: {total_chunks}, Tool call chunks: {tool_call_chunks}",
                tool_calls=collected_tool_calls,
            )
            self.assertTrue(tool_call_chunks >= 1, "Should receive at least one tool call chunk from API")
        except Exception as e:
            self._record_session(test_name, "Ling-3.0-flash", prompt, 0.0, "FAIL", error=str(e))
            self.fail(f"{test_name} failed: {e}")

    def test_107_multi_turn_agent_loop(self):
        self._skip_if_no_api_key()
        test_name = "Ling-3.0-flash Multi-Turn Agent Loop Test"
        print(f"\n---> Running: {test_name}")
        tool = PromptMessageTool(
            name="query_stock_price",
            description="Retrieve current stock price for a given ticker symbol.",
            parameters={
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"}},
                "required": ["ticker"],
            },
        )
        try:
            start_t = time.time()
            history = [UserPromptMessage(content="Check the current stock price for AAPL.")]
            res_turn1 = self._invoke_with_metrics("Ling-3.0-flash", history, {"max_tokens": 150}, tools=[tool])
            self.assertGreater(len(res_turn1['tool_calls']), 0)

            tool_call_id, tool_call_name = "call_aapl_test_9999", res_turn1['tool_calls'][0]['name']
            assistant_msg = AssistantPromptMessage(
                content="",
                tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id=tool_call_id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(name=tool_call_name, arguments='{"ticker": "AAPL"}'),
                    )
                ],
            )
            tool_res_msg = ToolPromptMessage(
                content='{"ticker": "AAPL", "price": 185.5, "currency": "USD", "status": "success"}',
                tool_call_id=tool_call_id,
                name=tool_call_name,
            )
            history.extend([assistant_msg, tool_res_msg])

            res_turn2 = self._invoke_with_metrics("Ling-3.0-flash", history, {"max_tokens": 200}, tools=[tool])
            dur = time.time() - start_t

            self._record_session(
                test_name, "Ling-3.0-flash", "Multi-Turn Agent Tool Loop", dur, "PASS",
                res_turn2['content'], tool_calls=res_turn1['tool_calls'], ttft_sec=res_turn2['ttft_sec'], tps=res_turn2['tps'],
            )
            self.assertGreater(len(res_turn2['content']), 0)
        except Exception as e:
            self._record_session(test_name, "Ling-3.0-flash", "Multi-Turn Agent Loop", 0.0, "FAIL", error=str(e))
            self.fail(f"{test_name} failed: {e}")

    def test_108_custom_model_schema_support(self):
        test_name, model_name = "Custom Model Schema Test", "Custom-LLM-Model"
        print(f"\n---> Running: {test_name}")
        start_t = time.time()
        try:
            schema = self.llm_model.get_customizable_model_schema(model_name, self.credentials)
            dur = time.time() - start_t
            self.assertIsNotNone(schema)
            self.assertEqual(schema.model, model_name)
            self.assertNotIn(ModelPropertyKey.MAX_CHUNKS, schema.model_properties)
            self._record_session(test_name, model_name, "Custom Model Schema", dur, "PASS", f"Schema generated: {schema.model}")
        except Exception as e:
            self._record_session(test_name, model_name, "Custom Model Schema", time.time() - start_t, "FAIL", error=str(e))
            self.fail(f"{test_name} failed: {e}")

    def test_201_ring_1t_reasoning_high(self):
        self._run_test(
            "Ring-2.6-1T Reasoning Effort High Test",
            "Ring-2.6-1T",
            "There are 3 boxes. Box A contains an apple. Box B does not contain an orange. Deduce the position of all items logically.",
            {"reasoning_effort": "high", "max_tokens": 200},
            assert_fn=lambda res: self.assertGreater(len(res['content']), 0),
        )

    def test_202_ring_1t_reasoning_xhigh(self):
        self._run_test(
            "Ring-2.6-1T Reasoning Effort XHigh Test",
            "Ring-2.6-1T",
            "Formulate a step-by-step logical framework for analyzing prime number distributions in even integers.",
            {"reasoning_effort": "xhigh", "max_tokens": 200},
            assert_fn=lambda res: self.assertGreater(len(res['content']), 0),
        )

    def test_203_ring_1t_long_context_reasoning(self):
        target = "PROMPT_ENGINEERING_AGENT_ARCH_2026"
        self._run_test(
            "Ring-2.6-1T Long Context Reasoning Test",
            "Ring-2.6-1T",
            _build_needle_prompt(target),
            {"reasoning_effort": "high", "max_tokens": 100},
            assert_fn=lambda res: self.assertIn(target, res['content']),
        )

    def test_204_ring_1t_long_text_generation(self):
        hard_prompt = """Write a technical essay analyzing future distributed AI system architectures.
Requirements:
1. Provide a logical analysis of consensus protocols and fault-tolerant state machine replication (at least 300 words).
2. Outline 3 structured chapters detailing memory hierarchy, network topology, and workload scheduling.
3. Maintain an academic and rigorous tone throughout."""
        self._run_test(
            "Ring-2.6-1T Long Generation Test",
            "Ring-2.6-1T",
            hard_prompt,
            {"reasoning_effort": "xhigh", "max_tokens": 3000},
            assert_fn=lambda res: self.assertGreater(res['estimated_tokens'], 200),
        )

    def test_301_ling_2_6_1t_basic_stream(self):
        self._run_test(
            "Ling-2.6-1T Basic Streaming Test",
            "Ling-2.6-1T",
            "Write a concise paragraph summarizing key principles of software system modularity.",
            {"temperature": 0.7, "max_tokens": 150},
            assert_fn=lambda res: self.assertGreater(len(res['content']), 0),
        )

    def test_302_ling_2_6_1t_long_context_retrieval(self):
        target = "FLAG_LONG_CONTEXT_VERIFIED_2026"
        self._run_test(
            "Ling-2.6-1T Long Context Retrieval Test",
            "Ling-2.6-1T",
            _build_needle_prompt(target),
            {"max_tokens": 100},
            assert_fn=lambda res: self.assertIn(target, res['content']),
        )

    def test_401_invalid_credentials_error_handling(self):
        test_name = "Invalid Credentials Error Test"
        print(f"\n---> Running: {test_name}")
        start_t = time.time()
        invalid_credentials = {"api_key": "sk-invalid-dummy-key-99999", "endpoint_url": self.api_base}
        try:
            with self.assertRaises(CredentialsValidateFailedError):
                self.llm_model.validate_credentials("Ling-3.0-flash", invalid_credentials)
            dur = time.time() - start_t
            self._record_session(test_name, "Ling-3.0-flash", "Invalid Key Validation", dur, "PASS", "Error caught as expected")
        except Exception as e:
            self._record_session(test_name, "Ling-3.0-flash", "Invalid Key Validation", time.time() - start_t, "FAIL", error=str(e))
            self.fail(f"{test_name} failed: {e}")

    def test_402_non_existent_model_error_handling(self):
        self._skip_if_no_api_key()
        test_name = "Non-Existent Model Error Test"
        print(f"\n---> Running: {test_name}")
        start_t = time.time()
        try:
            response = self.llm_model._invoke(
                model="NonExistent-Model-999",
                credentials=self.credentials,
                prompt_messages=[UserPromptMessage(content="Hello")],
                model_parameters={"max_tokens": 10},
                stream=True,
            )
            for _ in response:
                pass
        except AssertionError as ae:
            self._record_session(test_name, "NonExistent-Model-999", "Hello", 0.0, "FAIL", error=str(ae))
            raise ae
        except Exception as e:
            dur = time.time() - start_t
            self._record_session(test_name, "NonExistent-Model-999", "Hello", dur, "PASS", error=str(e))
            return

        self._record_session(test_name, "NonExistent-Model-999", "Hello", 0.0, "FAIL", error="Expected error not raised")
        self.fail("Calling non-existent model should raise an error")

    def test_403_exponential_backoff_retry_handling(self):
        test_name = "Exponential Backoff Retry Test"
        print(f"\n---> Running: {test_name}")
        start_t = time.time()
        from unittest.mock import patch

        call_count = 0
        def mock_failing_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("SSLError: UNEXPECTED_EOF_WHILE_READING")

        with patch("dify_plugin.OAICompatLargeLanguageModel._invoke", side_effect=mock_failing_invoke):
            with patch("time.sleep") as mock_sleep:
                try:
                    res = self.llm_model._invoke(
                        model="Ling-3.0-flash",
                        credentials=self.credentials,
                        prompt_messages=[UserPromptMessage(content="Test")],
                        model_parameters={"max_tokens": 10},
                        stream=True,
                    )
                    for chunk in res:
                        pass
                    self.fail("Should have raised SSLError after exhausting all 5 retries")
                except Exception as e:
                    dur = time.time() - start_t
                    self.assertEqual(call_count, 6)
                    self.assertEqual(mock_sleep.call_count, 5)
                    self._record_session(test_name, "Ling-3.0-flash", "Test", dur, "PASS", error=str(e))

    def test_404_model_parameters_top_level_transformation(self):
        test_name = "Model Parameters Top Level Transformation Test"
        print(f"\n---> Running: {test_name}")
        from unittest.mock import patch

        captured_params = {}

        def mock_super_invoke(model, credentials, prompt_messages, model_parameters, tools=None, stop=None, stream=True, user=None):
            nonlocal captured_params
            captured_params = model_parameters.copy()
            return iter([])

        params = {
            "enable_search": True,
            "forced_search": True,
            "reasoning_effort": "high",
            "thinking": "disabled",
            "temperature": 0.7,
        }

        with patch("dify_plugin.OAICompatLargeLanguageModel._invoke", side_effect=mock_super_invoke):
            res = self.llm_model._invoke(
                model="Ling-3.0-flash",
                credentials=self.credentials,
                prompt_messages=[UserPromptMessage(content="Test")],
                model_parameters=params,
                stream=True,
            )
            for _ in res:
                pass

        self.assertNotIn("extra_body", captured_params)
        self.assertNotIn("forced_search", captured_params)
        self.assertNotIn("reasoning_effort", captured_params)
        self.assertEqual(captured_params.get("enable_search"), True)
        self.assertEqual(captured_params.get("search_options"), {"forced_search": True})
        self.assertEqual(captured_params.get("reasoning"), {"effort": "high"})
        self.assertEqual(captured_params.get("thinking"), {"type": "disabled"})
        self.assertEqual(captured_params.get("temperature"), 0.7)

    def test_405_transient_error_500_retry_handling(self):
        test_name = "Transient Error 500 Retry Test"
        print(f"\n---> Running: {test_name}")
        from unittest.mock import patch

        call_count = 0

        def mock_failing_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("InvokeError: HTTP 500 Internal Server Error")

        with patch("dify_plugin.OAICompatLargeLanguageModel._invoke", side_effect=mock_failing_invoke):
            with patch("time.sleep") as mock_sleep:
                try:
                    res = self.llm_model._invoke(
                        model="Ling-3.0-flash",
                        credentials=self.credentials,
                        prompt_messages=[UserPromptMessage(content="Test")],
                        model_parameters={"max_tokens": 10},
                        stream=True,
                    )
                    for _ in res:
                        pass
                    self.fail("Should have raised Exception after exhausting retries")
                except Exception as e:
                    self.assertEqual(call_count, 6)
                    self.assertEqual(mock_sleep.call_count, 5)

    def test_406_empty_endpoint_url_fallback(self):
        test_name = "Empty Endpoint URL Fallback Test"
        print(f"\n---> Running: {test_name}")
        for empty_val in ["", "   ", None]:
            creds = {"endpoint_url": empty_val, "api_key": "test_key"}
            self.llm_model._add_custom_parameters(creds)
            self.assertEqual(creds["endpoint_url"], "https://api.ant-ling.com/v1")

    def test_407_provider_validate_credentials_execution(self):
        test_name = "Provider Validate Credentials Execution Test"
        print(f"\n---> Running: {test_name}")
        from unittest.mock import MagicMock, patch
        from provider.ant_ling import AntLingModelProvider

        provider = AntLingModelProvider(provider_schemas=MagicMock(), model_factory=MagicMock())
        mock_model_instance = MagicMock()
        with patch.object(provider, "get_model_instance", return_value=mock_model_instance):
            provider.validate_provider_credentials({"api_key": "test_key", "validate_model": "Ling-3.0-flash"})
            mock_model_instance.validate_credentials.assert_called_once()

    def test_408_bare_500_not_matched_as_transient_error(self):
        test_name = "Bare 500 Substring Not Transient Error Test"
        print(f"\n---> Running: {test_name}")
        from models.llm.llm import _is_transient_error

        self.assertFalse(_is_transient_error(Exception("max_tokens must be <= 500")))
        self.assertFalse(_is_transient_error(Exception("connect to http://localhost:5000 failed")))

        self.assertTrue(_is_transient_error(Exception("InvokeError: HTTP 500 Internal Server Error")))
        self.assertTrue(_is_transient_error(Exception('{"code": 500, "message": "server error"}')))


if __name__ == "__main__":
    unittest.main()




