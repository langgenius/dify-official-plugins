from types import SimpleNamespace
from unittest.mock import MagicMock

import dify_plugin  # noqa: F401 - initialize the runtime before HTTP clients
import pytest
import snowflake.connector

from provider.snowflake_sql import SnowflakeSQLProvider
from tools.snowflake_sql import SnowflakeQueryTool


@pytest.mark.parametrize("query", [False, True])
def test_oauth_connections_disable_shared_credential_cache(monkeypatch, query):
    credentials = {"account_name": "test-account", "access_token": "test-token"}
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.description = [("VALUE",)]
    cursor.fetchmany.return_value = [(7,)]
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(snowflake.connector, "connect", connect)

    if query:
        tool = object.__new__(SnowflakeQueryTool)
        tool.runtime = SimpleNamespace(credentials=credentials)
        tool.create_json_message = lambda value: value
        tool.create_text_message = lambda value: value
        tool.create_variable_message = lambda name, value: (name, value)
        messages = list(tool._invoke({"sql_query": "SELECT VALUE FROM SAMPLE", "max_rows": 1}))
        assert messages[0]["rows"] == [{"VALUE": 7}]
        cursor.execute.assert_called_once_with("SELECT VALUE FROM SAMPLE")
    else:
        provider = object.__new__(SnowflakeSQLProvider)
        provider._validate_credentials(credentials)
        cursor.execute.assert_called_once_with("SELECT CURRENT_USER()")

    assert connect.call_args.kwargs["account"] == "test-account"
    assert connect.call_args.kwargs["token"] == "test-token"
    assert connect.call_args.kwargs["authenticator"] == "oauth"
    assert connect.call_args.kwargs["client_store_temporary_credential"] is False
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
