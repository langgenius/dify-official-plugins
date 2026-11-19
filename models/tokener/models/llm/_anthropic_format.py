from dify_plugin.entities.model.message import AssistantPromptMessage, SystemPromptMessage


def code_block_mode(
    owner,
    model,
    credentials,
    prompt_messages,
    model_parameters,
    tools,
    stop,
    stream,
    user,
    adaptive,
):
    mode = model_parameters.pop("response_format", None)
    schema = model_parameters.get("json_schema")
    has_schema = schema is not None and (not isinstance(schema, str) or bool(schema.strip()))
    if mode and not (mode == "JSON" and has_schema):
        template = (
            "You should always follow the instructions and output a valid "
            f"{mode} object.\nThe structure of the {mode} object you can found in the "
            'instructions, use {"answer": "$your_answer"} as the default structure\n'
            "if you are not sure about the structure.\n\n<instructions>\n"
        )
        if prompt_messages and isinstance(prompt_messages[0], SystemPromptMessage):
            instructions = str(prompt_messages[0].content)
            prompt_messages[0] = SystemPromptMessage(
                content=template + instructions + "\n</instructions>\n"
            )
        else:
            prompt_messages.insert(
                0,
                SystemPromptMessage(
                    content=template + f"Please output a valid {mode} object.\n</instructions>\n"
                ),
            )
        if not adaptive:
            prompt_messages.append(AssistantPromptMessage(content=f"\n```{mode}"))
        if stop:
            for marker in ("```\n", "\n```"):
                if marker not in stop:
                    stop.append(marker)
        model_parameters.pop("json_schema", None)
    return owner._invoke(
        model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    )
