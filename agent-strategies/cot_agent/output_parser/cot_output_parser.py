import json
from collections.abc import Generator
from enum import Enum
from typing import Union

from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.interfaces.agent import AgentScratchpadUnit


class ReactState(Enum):
    THINKING = ("thought:", "THINKING")
    ACTION = ("action:", "ACTION")
    ANSWER = ("answer:", "ANSWER")
    IDLE = (None, "IDLE")

    def __init__(self, prefix: str, state: str):
        self.prefix = prefix
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
        json_quote_count = 0
        in_json = False
        got_json = False

        action_cache = ""
        action_str = ReactState.ACTION.prefix
        action_idx = 0

        thought_cache = ""
        thought_str = ReactState.THINKING.prefix
        thought_idx = 0

        answer_cache = ""
        answer_str = ReactState.ANSWER.prefix
        answer_idx = 0

        cur_state = ReactState.THINKING
        last_character = ""

        for response in llm_response:
            if response.delta.usage:
                usage_dict["usage"] = response.delta.usage
            response_content = response.delta.message.content
            if not isinstance(response_content, str):
                continue

            # stream
            index = 0
            while index < len(response_content):
                steps = 1
                delta = response_content[index: index + steps]
                yield_delta = False

                if not in_json:
                    if delta.lower() == action_str[action_idx] and action_idx == 0:
                        if last_character not in {"\n", " ", ""}:
                            yield_delta = True
                        else:
                            last_character = delta
                            action_cache += delta
                            action_idx += 1
                            if action_idx == len(action_str):
                                action_cache = ""
                                action_idx = 0
                            index += steps
                            continue
                    elif delta.lower() == action_str[action_idx] and action_idx > 0:
                        last_character = delta
                        action_cache += delta
                        action_idx += 1
                        if action_idx == len(action_str):
                            action_cache = ""
                            action_idx = 0
                        index += steps
                        continue
                    else:
                        if action_cache:
                            last_character = delta
                            yield ReactChunk(cur_state, action_cache)
                            action_cache = ""
                            action_idx = 0

                    if delta.lower() == answer_str[answer_idx] and answer_idx == 0:
                        if last_character not in {"\n", " ", ""}:
                            yield_delta = True
                        else:
                            last_character = delta
                            answer_cache += delta
                            answer_idx += 1
                            if answer_idx == len(answer_str):
                                answer_cache = ""
                                answer_idx = 0
                            index += steps
                            continue
                    elif delta.lower() == answer_str[answer_idx] and answer_idx > 0:
                        last_character = delta
                        answer_cache += delta
                        answer_idx += 1
                        if answer_idx == len(answer_str):
                            answer_cache = ""
                            answer_idx = 0
                            cur_state = ReactState.ANSWER
                        index += steps
                        continue
                    else:
                        if answer_cache:
                            last_character = delta
                            yield ReactChunk(cur_state, answer_cache)
                            answer_cache = ""
                            answer_idx = 0

                    if delta.lower() == thought_str[thought_idx] and thought_idx == 0:
                        if last_character not in {"\n", " ", ""}:
                            yield_delta = True
                        else:
                            last_character = delta
                            thought_cache += delta
                            thought_idx += 1
                            if thought_idx == len(thought_str):
                                thought_cache = ""
                                thought_idx = 0
                            index += steps
                            continue
                    elif delta.lower() == thought_str[thought_idx] and thought_idx > 0:
                        last_character = delta
                        thought_cache += delta
                        thought_idx += 1
                        if thought_idx == len(thought_str):
                            thought_cache = ""
                            thought_idx = 0
                            cur_state = ReactState.THINKING
                        index += steps
                        continue
                    else:
                        if thought_cache:
                            last_character = delta
                            yield ReactChunk(cur_state, thought_cache)
                            thought_cache = ""
                            thought_idx = 0

                    if yield_delta:
                        index += steps
                        last_character = delta
                        yield ReactChunk(cur_state, delta)
                        continue

                # handle single json
                if delta == "{":
                    json_quote_count += 1
                    in_json = True
                    last_character = delta
                    json_cache += delta
                elif delta == "}":
                    last_character = delta
                    json_cache += delta
                    if json_quote_count > 0:
                        json_quote_count -= 1
                        if json_quote_count == 0:
                            in_json = False
                            got_json = True
                            index += steps
                            continue
                else:
                    if in_json:
                        last_character = delta
                        json_cache += delta

                if got_json:
                    got_json = False
                    last_character = delta
                    parsed_result = parse_action(json_cache)
                    if isinstance(parsed_result, AgentScratchpadUnit.Action):
                        yield parsed_result
                    else:
                        yield ReactChunk(cur_state, json_cache)
                    json_cache = ""
                    json_quote_count = 0
                    in_json = False

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
