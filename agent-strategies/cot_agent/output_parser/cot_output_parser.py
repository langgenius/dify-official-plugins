import json
from collections.abc import Generator
from enum import Enum
from typing import Union

from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.interfaces.agent import AgentScratchpadUnit

PREFIX_DELIMITERS = frozenset({"\n", " ", ""})
# Tags injected by Gemini when include_thoughts=True; stripped so ReAct sees only Thought:/Action:/FinalAnswer:
THINK_START = "<think>"
THINK_END = "</think>"


class ReactState(Enum):
    THINKING = ("Thought:", "THINKING")
    ANSWER = ("FinalAnswer:", "ANSWER")

    def __init__(self, prefix: str, state: str):
        self.prefix = prefix
        self.prefix_lower = prefix.lower()
        self.state = state


class ReactChunk:
    def __init__(self, state: ReactState, content: str):
        self.state = state
        self.content = content


class CotAgentOutputParser:
    @classmethod
    def handle_react_stream_output(
        cls, llm_response: Generator[LLMResultChunk, None, None], usage_dict: dict
    ) -> Generator[Union[ReactChunk, AgentScratchpadUnit.Action], None, None]:
        def parse_action(json_str):
            try:
                action = json.loads(json_str, strict=False)
                action_name = None
                action_input = None

                # cohere always returns a list
                if isinstance(action, list) and len(action) == 1:
                    action = action[0]

                for key, value in action.items():
                    if "input" in key.lower():
                        action_input = value
                    else:
                        action_name = value

                if action_name is not None and action_input is not None:
                    return AgentScratchpadUnit.Action(
                        action_name=action_name,
                        action_input=action_input,
                    )
                else:
                    return json_str or ""
            except Exception:
                return json_str or ""

        json_cache = ""
        in_json = False
        got_json = False

        json_in_string = False
        json_escape = False
        pending_action_json = False
        json_stack: list[str] = []

        cur_state = ReactState.THINKING
        last_character = ""

        class PrefixMatcher:
            __slots__ = ("prefix", "state_on_full_match", "cache", "idx")

            def __init__(self, spec: ReactState | str):
                if isinstance(spec, ReactState):
                    self.prefix = spec.prefix_lower
                    self.state_on_full_match = spec
                else:
                    self.prefix = spec.lower()
                    self.state_on_full_match = None
                self.cache = ""
                self.idx = 0

            def step(self, delta: str) -> tuple[bool, ReactChunk | None, bool, bool]:
                nonlocal last_character, cur_state

                yield_raw_delta = False
                emitted_chunk = None
                delta_consumed = False
                matched_full_prefix = False

                if delta.lower() == self.prefix[self.idx]:
                    if self.idx == 0 and last_character not in PREFIX_DELIMITERS:
                        yield_raw_delta = True
                    else:
                        last_character = delta
                        self.cache += delta
                        self.idx += 1
                        if self.idx == len(self.prefix):
                            self.cache = ""
                            self.idx = 0
                            if self.state_on_full_match is not None:
                                cur_state = self.state_on_full_match
                            matched_full_prefix = True
                        delta_consumed = True
                elif self.cache:
                    last_character = delta
                    emitted_chunk = ReactChunk(cur_state, self.cache)
                    self.cache = ""
                    self.idx = 0

                return yield_raw_delta, emitted_chunk, delta_consumed, matched_full_prefix

        action_matcher = PrefixMatcher("action:")
        answer_matcher = PrefixMatcher(ReactState.ANSWER)
        thought_matcher = PrefixMatcher(ReactState.THINKING)

        _in_think = False
        _think_buf = ""
        _think_depth = 0
        for response in llm_response:
            if response.delta.usage:
                usage_dict["usage"] = response.delta.usage
            raw = response.delta.message.content
            if isinstance(raw, str):
                response_content = raw
            elif isinstance(raw, list):
                # Plugins (e.g. Gemini) send content as list; some items may be non-text (e.g. image)
                parts = [
                    s
                    for c in raw
                    if isinstance(s := (getattr(c, "data", None) or getattr(c, "text", None)), str)
                ]
                response_content = "".join(parts)
            else:
                continue
            if not response_content:
                continue
            # When include_thoughts=True, Gemini injects <think>...</think>; strip across chunks so
            # ReAct parser only sees Thought:/Action:/FinalAnswer: from the model reply.
            # Nested <think> tags are supported via a depth counter.
            if THINK_START in response_content or THINK_END in response_content or _in_think:
                buf = _think_buf + response_content
                _think_buf = ""
                out = []
                i = 0
                while i < len(buf):
                    if _in_think:
                        end_j = buf.find(THINK_END, i)
                        start_j = buf.find(THINK_START, i)
                        if end_j == -1 and start_j == -1:
                            _think_buf = buf[i:]
                            break
                        if start_j != -1 and (end_j == -1 or start_j < end_j):
                            _think_depth += 1
                            i = start_j + len(THINK_START)
                        else:
                            j = end_j
                            _think_depth -= 1
                            if _think_depth <= 0:
                                _in_think = False
                                _think_depth = 0
                            i = j + len(THINK_END)
                    else:
                        j = buf.find(THINK_START, i)
                        if j == -1:
                            out.append(buf[i:])
                            break
                        out.append(buf[i:j])
                        _in_think = True
                        _think_depth = 1
                        i = j + len(THINK_START)
                response_content = "".join(out)
            if not response_content:
                continue

            # stream
            index = 0
            while index < len(response_content):
                steps = 1
                delta = response_content[index: index + steps]
                yield_delta = False

                if not in_json:
                    yield_raw_delta, emitted_chunk, delta_consumed, matched_action_prefix = action_matcher.step(delta)
                    if emitted_chunk is not None:
                        yield emitted_chunk
                    yield_delta = yield_delta or yield_raw_delta
                    if matched_action_prefix:
                        pending_action_json = True
                    if delta_consumed:
                        index += steps
                        continue

                    yield_raw_delta, emitted_chunk, delta_consumed, _ = answer_matcher.step(delta)
                    if emitted_chunk is not None:
                        yield emitted_chunk
                    yield_delta = yield_delta or yield_raw_delta
                    if delta_consumed:
                        index += steps
                        continue

                    yield_raw_delta, emitted_chunk, delta_consumed, _ = thought_matcher.step(delta)
                    if emitted_chunk is not None:
                        yield emitted_chunk
                    yield_delta = yield_delta or yield_raw_delta
                    if delta_consumed:
                        index += steps
                        continue

                    if yield_delta:
                        index += steps
                        last_character = delta
                        yield ReactChunk(cur_state, delta)
                        continue

                if not in_json and pending_action_json:
                    if delta in {"{", "["}:
                        in_json = True
                        got_json = False
                        json_cache = delta
                        json_in_string = False
                        json_escape = False
                        json_stack = ["}" if delta == "{" else "]"]
                        last_character = delta
                        index += steps
                        continue
                    if not delta.isspace():
                        pending_action_json = False

                if in_json:
                    last_character = delta
                    json_cache += delta

                    if json_in_string:
                        if json_escape:
                            json_escape = False
                        elif delta == "\\":
                            json_escape = True
                        elif delta == '"':
                            json_in_string = False
                    else:
                        if delta == '"':
                            json_in_string = True
                        elif delta in {"{", "["}:
                            json_stack.append("}" if delta == "{" else "]")
                        elif delta in {"}", "]"} and json_stack and delta == json_stack[-1]:
                            json_stack.pop()
                            if not json_stack:
                                in_json = False
                                got_json = True
                                pending_action_json = False
                                index += steps
                                continue

                if got_json:
                    got_json = False
                    last_character = delta
                    parsed_result = parse_action(json_cache)
                    if isinstance(parsed_result, AgentScratchpadUnit.Action):
                        yield parsed_result
                    else:
                        yield ReactChunk(cur_state, json_cache)
                    json_cache = ""
                    in_json = False
                    json_in_string = False
                    json_escape = False
                    json_stack = []

                if not in_json:
                    last_character = delta
                    yield ReactChunk(cur_state, delta)

                index += steps

        if json_cache:
            parsed_result = parse_action(json_cache)
            if isinstance(parsed_result, AgentScratchpadUnit.Action):
                yield parsed_result
            else:
                yield ReactChunk(cur_state, json_cache)
