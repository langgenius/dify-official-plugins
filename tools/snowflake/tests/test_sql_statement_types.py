from types import SimpleNamespace
from unittest.mock import MagicMock

import dify_plugin  # noqa: F401 - initialize the runtime before HTTP clients
import pytest
import snowflake.connector

from tools.snowflake_sql import SnowflakeQueryTool


@pytest.fixture
def tool():
    return object.__new__(SnowflakeQueryTool)


@pytest.mark.parametrize(
    ("query", "sql_type"),
    [
        ("CREATE SCHEMA EXAMPLE_SCHEMA", "CREATE"),
        ("CREATE SCHEMA IF NOT EXISTS EXAMPLE_SCHEMA", "CREATE"),
        ("CREATE OR REPLACE SCHEMA EXAMPLE_SCHEMA", "CREATE"),
        ("CREATE TABLE EXAMPLE_TABLE (ID INTEGER)", "CREATE"),
        ("CREATE OR REPLACE TABLE EXAMPLE_TABLE (ID INTEGER)", "CREATE"),
        ("CREATE TEMPORARY TABLE EXAMPLE_TABLE (ID INTEGER)", "CREATE"),
        ("CREATE TRANSIENT TABLE EXAMPLE_TABLE (ID INTEGER)", "CREATE"),
        ("CREATE TABLE EXAMPLE_TABLE AS SELECT 1 AS ID", "CREATE"),
        ("CREATE OR REPLACE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID", "CREATE"),
        ("CREATE SECURE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID", "CREATE"),
        ("CREATE OR REPLACE SECURE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID", "CREATE"),
        ("create or replace view example_view as select 1 as id", "CREATE"),
        ("CREATE\nOR\nREPLACE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID", "CREATE"),
        ("-- Example comment\nCREATE SCHEMA EXAMPLE_SCHEMA", "CREATE"),
        ("CREATE -- Example comment\nSCHEMA EXAMPLE_SCHEMA", "CREATE"),
        ("DROP TABLE EXAMPLE_TABLE", "DROP"),
        ("DROP -- Example comment\nTABLE EXAMPLE_TABLE", "DROP"),
        ("ALTER TABLE EXAMPLE_TABLE ADD COLUMN LABEL VARCHAR", "ALTER"),
        ("ALTER -- Example comment\nTABLE EXAMPLE_TABLE ADD COLUMN LABEL VARCHAR", "ALTER"),
        ("TRUNCATE TABLE EXAMPLE_TABLE", "TRUNCATE"),
        ("SELECT ID FROM EXAMPLE_TABLE", "SELECT"),
        ("SHOW TABLES", "SHOW"),
        ("DESCRIBE TABLE EXAMPLE_TABLE", "DESCRIBE"),
        ("INSERT INTO EXAMPLE_TABLE (ID) VALUES (1)", "INSERT"),
        ("UPDATE EXAMPLE_TABLE SET ID = 2 WHERE ID = 1", "UPDATE"),
        ("DELETE FROM EXAMPLE_TABLE WHERE ID = 1", "DELETE"),
    ],
)
def test_statement_type_accepts_the_leading_verb(tool, query, sql_type):
    assert tool._validate_sql_query(query, sql_type) == (True, "")


@pytest.mark.parametrize(
    ("query", "declared_type", "detected_type"),
    [
        ("CREATE SCHEMA EXAMPLE_SCHEMA", "SELECT", "CREATE"),
        ("CREATE TABLE EXAMPLE_TABLE AS SELECT 1 AS ID", "SELECT", "CREATE"),
        ("CREATE OR REPLACE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID", "SELECT", "CREATE"),
        ("DROP TABLE EXAMPLE_TABLE", "CREATE", "DROP"),
        ("ALTER TABLE EXAMPLE_TABLE ADD COLUMN LABEL VARCHAR", "SELECT", "ALTER"),
        ("SELECT ID FROM EXAMPLE_TABLE", "CREATE", "SELECT"),
    ],
)
def test_type_mismatches_still_rejected(tool, query, declared_type, detected_type):
    valid, error = tool._validate_sql_query(query, declared_type)
    assert not valid
    assert f"declared as {declared_type} but detected as {detected_type}" in error


@pytest.mark.parametrize(
    ("query", "sql_type"),
    [
        ("GRANT SELECT ON TABLE EXAMPLE_TABLE TO ROLE EXAMPLE_ROLE", "OTHER"),
        ("REVOKE SELECT ON TABLE EXAMPLE_TABLE FROM ROLE EXAMPLE_ROLE", "OTHER"),
        ("CREATE USER EXAMPLE_USER", "CREATE"),
        ("CREATE OR REPLACE USER EXAMPLE_USER", "CREATE"),
        ("CREATE -- Example comment\nUSER EXAMPLE_USER", "CREATE"),
        ("CREATE OR REPLACE -- Example comment\nUSER EXAMPLE_USER", "CREATE"),
        ("CREATE ROLE EXAMPLE_ROLE", "CREATE"),
        ("CREATE -- Example comment\nROLE EXAMPLE_ROLE", "CREATE"),
        ("DROP USER EXAMPLE_USER", "DROP"),
        ("DROP -- Example comment\nUSER EXAMPLE_USER", "DROP"),
        ("DROP ROLE EXAMPLE_ROLE", "DROP"),
        ("DROP -- Example comment\nROLE EXAMPLE_ROLE", "DROP"),
        ("ALTER USER EXAMPLE_USER SET DISABLED = TRUE", "ALTER"),
        ("ALTER -- Example comment\nUSER EXAMPLE_USER SET DISABLED = TRUE", "ALTER"),
        ("DROP USER EXAMPLE_USER", "OTHER"),
        ("DROP ROLE EXAMPLE_ROLE", "OTHER"),
        ("ALTER USER EXAMPLE_USER SET DISABLED = TRUE", "OTHER"),
        ("DROP -- Example comment\nROLE EXAMPLE_ROLE", "OTHER"),
        ("CREATE WAREHOUSE EXAMPLE_WAREHOUSE", "CREATE"),
        ("CREATE -- Example comment\nWAREHOUSE EXAMPLE_WAREHOUSE", "CREATE"),
        ("CREATE NETWORK POLICY EXAMPLE_POLICY ALLOWED_IP_LIST = ('127.0.0.1')", "CREATE"),
        ("CREATE -- Example comment\nNETWORK POLICY EXAMPLE_POLICY", "CREATE"),
        ("ALTER ACCOUNT SET TIMEZONE = 'UTC'", "ALTER"),
        ("ALTER -- Example comment\nACCOUNT SET TIMEZONE = 'UTC'", "ALTER"),
        ("CREATE FUNCTION EXAMPLE_FUNCTION() RETURNS INT AS '1'", "CREATE"),
        ("CREATE -- Example comment\nFUNCTION EXAMPLE_FUNCTION() RETURNS INT AS '1'", "CREATE"),
        ("CREATE -- Example comment\nFUNCTION EXAMPLE_FUNCTION() RETURNS INT AS '1'", "OTHER"),
        ("CREATE OR REPLACE SECURE FUNCTION EXAMPLE_FUNCTION() RETURNS INT AS '1'", "CREATE"),
        ("CREATE PROCEDURE EXAMPLE_PROCEDURE() RETURNS INT LANGUAGE SQL AS 'SELECT 1'", "CREATE"),
        (
            "CREATE -- Example comment\nPROCEDURE EXAMPLE_PROCEDURE() RETURNS INT LANGUAGE SQL AS 'SELECT 1'",
            "CREATE",
        ),
        ("CREATE EXTERNAL TABLE EXAMPLE_TABLE (ID INT)", "CREATE"),
        ("SELECT SYSTEM$WAIT(1)", "SELECT"),
        ("GET @EXAMPLE_STAGE file://example-directory", "OTHER"),
    ],
)
def test_restricted_operations_remain_rejected(tool, query, sql_type):
    valid, error = tool._validate_sql_query(query, sql_type)
    assert not valid
    assert error


@pytest.mark.parametrize(
    "query",
    [
        "CREATE SCHEMA EXAMPLE_SCHEMA; SELECT 1",
        "CREATE TABLE EXAMPLE_TABLE (ID INTEGER); DROP TABLE EXAMPLE_TABLE",
        "SELECT 1; SELECT 2",
    ],
)
def test_multiple_statements_remain_rejected(tool, query):
    valid, error = tool._validate_sql_query(query, "CREATE")
    assert not valid
    assert "Multiple SQL statements detected" in error


@pytest.mark.parametrize(
    ("query", "sql_type"),
    [
        ("CREATE /* Example comment */ SCHEMA EXAMPLE_SCHEMA", "CREATE"),
        ("DROP /* Example comment */ TABLE EXAMPLE_TABLE", "DROP"),
    ],
)
def test_block_comment_injection_rule_is_unchanged(tool, query, sql_type):
    valid, error = tool._validate_sql_query(query, sql_type)
    assert not valid
    assert "Block comment injection" in error


def configure_invocation(tool):
    tool.runtime = SimpleNamespace(
        credentials={"account_name": "test-account", "access_token": "test-token"}
    )
    tool.create_json_message = lambda value: value
    tool.create_text_message = lambda value: value
    tool.create_variable_message = lambda name, value: (name, value)


@pytest.mark.parametrize(
    "query",
    [
        "CREATE SCHEMA IF NOT EXISTS EXAMPLE_SCHEMA",
        "CREATE OR REPLACE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID",
        "CREATE SECURE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID",
        "CREATE OR REPLACE SECURE VIEW EXAMPLE_VIEW AS SELECT 1 AS ID",
        "CREATE TABLE EXAMPLE_TABLE AS SELECT 1 AS ID",
        "CREATE -- Example comment\nSCHEMA EXAMPLE_SCHEMA",
    ],
)
def test_valid_ddl_reaches_connector_and_returns_status(monkeypatch, tool, query):
    configure_invocation(tool)
    connection = MagicMock()
    cursor = connection.cursor.return_value
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(snowflake.connector, "connect", connect)

    messages = list(tool._invoke({"sql_query": query, "sql_type": "CREATE"}))

    assert messages[0]["success"] is True
    assert messages[0]["sql_type"] == "CREATE"
    assert messages[0]["executed_sql"] == query
    cursor.execute.assert_called_once_with(query)
    cursor.fetchmany.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
    assert connect.call_args.kwargs["client_store_temporary_credential"] is False


@pytest.mark.parametrize(
    ("query", "sql_type"),
    [
        ("DROP USER EXAMPLE_USER", "DROP"),
        ("DROP ROLE EXAMPLE_ROLE", "DROP"),
        ("ALTER USER EXAMPLE_USER SET DISABLED = TRUE", "ALTER"),
        ("CREATE FUNCTION EXAMPLE_FUNCTION() RETURNS INT AS '1'", "CREATE"),
        ("CREATE SCHEMA EXAMPLE_SCHEMA; SELECT 1", "CREATE"),
        ("DROP -- Example comment\nROLE EXAMPLE_ROLE", "DROP"),
    ],
)
def test_rejected_sql_does_not_open_connection(monkeypatch, tool, query, sql_type):
    configure_invocation(tool)
    connect = MagicMock()
    monkeypatch.setattr(snowflake.connector, "connect", connect)

    messages = list(tool._invoke({"sql_query": query, "sql_type": sql_type}))

    assert any(
        isinstance(message, dict) and message.get("success") is False for message in messages
    )
    connect.assert_not_called()
