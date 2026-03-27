
from dify_plugin.core.entities.plugin.request import (
    PluginInvokeType,
    ToolActions,
    ToolInvokeRequest,
)
from dify_plugin.entities.tool import ToolInvokeMessage

def test_json_parse(plugin_runner):
    """
    Test the json_process parse tool.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="parse",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"a": 1, "b": {"c": 2}}',
                "json_filter": "$.b.c",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # Check if the result is a text message with the extracted value
    assert response_chunks[0].message.text == "2"

def test_json_parse_complex(plugin_runner):
    """
    Test the json_process parse tool with complex object return.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="parse",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"a": 1, "b": {"c": 2}}',
                "json_filter": "$.b",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # Should return json string of the dict
    assert response_chunks[0].message.text == '{"c": 2}'

def test_json_parse_error(plugin_runner):
    """
    Test the json_process parse tool with invalid json.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="parse",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": 'invalid json',
                "json_filter": "$.b.c",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)
    
    # Based on the code, it catches generic Exception and returns "Failed to extract JSON content"
    # Wait, tools/parse.py catches Exception and create_text_message
    assert len(response_chunks) == 1
    # The tool returns the exception message from json.loads if parsing fails inside _extract
    assert "Expecting value" in response_chunks[0].message.text or "JSONDecodeError" in response_chunks[0].message.text


def test_json_delete(plugin_runner):
    """
    Test the json_process delete tool.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_delete",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"a": 1, "b": {"c": 2}}',
                "query": "$.b.c",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After deleting $.b.c, the result should be {"a": 1, "b": {}}
    assert response_chunks[0].message.text == '{"a": 1, "b": {}}'


def test_json_delete_array_element(plugin_runner):
    """
    Test the json_process delete tool with array element.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_delete",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"items": [1, 2, 3]}',
                "query": "$.items[1]",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After deleting items[1] (value 2), result should be {"items": [1, 3]}
    assert response_chunks[0].message.text == '{"items": [1, 3]}'


def test_json_insert_to_array(plugin_runner):
    """
    Test the json_process insert tool - append to array.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_insert",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"items": [1, 2]}',
                "query": "$.items",
                "new_value": "3",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After appending 3 to items, result should be {"items": [1, 2, "3"]}
    assert response_chunks[0].message.text == '{"items": [1, 2, "3"]}'


def test_json_insert_with_index(plugin_runner):
    """
    Test the json_process insert tool - insert at specific index.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_insert",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"items": [1, 3]}',
                "query": "$.items",
                "new_value": "2",
                "index": 1,
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After inserting "2" at index 1, result should be {"items": [1, "2", 3]}
    assert response_chunks[0].message.text == '{"items": [1, "2", 3]}'


def test_json_insert_create_path(plugin_runner):
    """
    Test the json_process insert tool - create path if not exists.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_insert",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"a": 1}',
                "query": "$.b.c",
                "new_value": "new_value",
                "create_path": True,
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After creating path $.b.c with value "new_value"
    assert response_chunks[0].message.text == '{"a": 1, "b": {"c": "new_value"}}'


def test_json_replace_value(plugin_runner):
    """
    Test the json_process replace tool - replace value mode.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_replace",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"a": 1, "b": 2}',
                "query": "$.a",
                "replace_value": "100",
                "replace_model": "value",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After replacing $.a with "100"
    assert response_chunks[0].message.text == '{"a": "100", "b": 2}'


def test_json_replace_key(plugin_runner):
    """
    Test the json_process replace tool - replace key mode.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_replace",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"old_key": 1, "b": 2}',
                "query": "$.old_key",
                "replace_value": "new_key",
                "replace_model": "key",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After replacing key "old_key" with "new_key"
    assert response_chunks[0].message.text == '{"b": 2, "new_key": 1}'


def test_json_replace_pattern(plugin_runner):
    """
    Test the json_process replace tool - replace pattern mode.
    """
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Tool,
        access_action=ToolActions.InvokeTool,
        payload=ToolInvokeRequest(
            provider="json_process",
            tool="json_replace",
            action=ToolActions.InvokeTool,
            credentials={},
            tool_parameters={
                "content": '{"message": "Hello World"}',
                "query": "$.message",
                "replace_pattern": "World",
                "replace_value": "Universe",
                "replace_model": "pattern",
                "ensure_ascii": True,
            },
            user_id="test_user",
            type=PluginInvokeType.Tool,
        ),
        response_type=ToolInvokeMessage,
    ):
        response_chunks.append(result)

    assert len(response_chunks) == 1
    # After replacing "World" with "Universe" in $.message
    assert response_chunks[0].message.text == '{"message": "Hello Universe"}'
