ENGLISH_REACT_COMPLETION_PROMPT_TEMPLATES = """Respond to the human as helpfully and accurately as possible.

{{instruction}}

You have access to the following tools:

{{tools}}

Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).
Valid "action" values: {{tool_names}}

Provide only ONE action per $JSON_BLOB, as shown:

{
  "action": $TOOL_NAME,
  "action_input": $ACTION_INPUT
}

Follow this format:

Thought: [your reasoning]
Action: {"action": "tool_name", "action_input": {"param": "value"}}
Observation: [tool output]
... (repeat as needed)
FinalAnswer: [your response]

Begin! Use "Action:" only when calling tools. End with "FinalAnswer:".
{{historic_messages}}
Question: {{query}}
{{agent_scratchpad}}
Thought:"""  # noqa: E501


ENGLISH_REACT_COMPLETION_AGENT_SCRATCHPAD_TEMPLATES = """Observation: {{observation}}
Thought:"""

ENGLISH_REACT_CHAT_PROMPT_TEMPLATES = """Respond to the human as helpfully and accurately as possible.

{{instruction}}

You have access to the following tools:

{{tools}}

Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).
Valid "action" values: {{tool_names}}

Provide only ONE action per $JSON_BLOB, as shown:

{
  "action": $TOOL_NAME,
  "action_input": $ACTION_INPUT
}

Follow this format:

Thought: [your reasoning]
Action: {"action": "tool_name", "action_input": {"param": "value"}}
Observation: [tool output]
... (repeat as needed)
FinalAnswer: [your response]

Begin! Use "Action:" only when calling tools. End with "FinalAnswer:".
"""  # noqa: E501


ENGLISH_REACT_CHAT_AGENT_SCRATCHPAD_TEMPLATES = ""

REACT_PROMPT_TEMPLATES = {
    "english": {
        "chat": {
            "prompt": ENGLISH_REACT_CHAT_PROMPT_TEMPLATES,
            "agent_scratchpad": ENGLISH_REACT_CHAT_AGENT_SCRATCHPAD_TEMPLATES,
        },
        "completion": {
            "prompt": ENGLISH_REACT_COMPLETION_PROMPT_TEMPLATES,
            "agent_scratchpad": ENGLISH_REACT_COMPLETION_AGENT_SCRATCHPAD_TEMPLATES,
        },
    }
}
