import time
from typing import Any, Generator

import snowflake.connector
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SnowflakeQueryTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Execute SQL query on Snowflake database using OAuth authentication.
        """
        sql_query = tool_parameters.get("sql_query", "")
        sql_type = tool_parameters.get("sql_type", "SELECT").upper()
        max_rows = tool_parameters.get("max_rows", 100)

        # Security check: Block dangerous SQL statements
        security_check = self._check_sql_security(sql_query)
        if not security_check["allowed"]:
            error_msg = security_check["error"]
            yield self.create_text_message(error_msg)
            yield self.create_json_message(
                {
                    "success": False,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "executed_sql": sql_query,
                    "execution_time": 0,
                    "error": error_msg,
                }
            )
            yield self.create_variable_message("success", False)
            yield self.create_variable_message("executed_sql", sql_query)
            yield self.create_variable_message("execution_time", 0)
            yield self.create_variable_message("error", error_msg)
            return

        # Get authentication credentials
        account_name = self.runtime.credentials.get("account_name")
        access_token = self.runtime.credentials.get("access_token")
        warehouse = tool_parameters.get("warehouse") or self.runtime.credentials.get(
            "warehouse",
        )
        database = tool_parameters.get("database") or self.runtime.credentials.get(
            "database",
        )
        schema = tool_parameters.get("schema") or self.runtime.credentials.get(
            "schema", "PUBLIC"
        )

        start_time = time.time()

        try:
            # Connect with OAuth authentication
            conn = snowflake.connector.connect(
                account=account_name,
                authenticator="oauth",
                token=access_token,
                warehouse=warehouse,
                database=database,
                schema=schema,
            )

            cursor = conn.cursor()
            cursor.execute(sql_query)

            execution_time = time.time() - start_time

            # Process results based on SQL type
            if sql_type in ["SELECT", "SHOW", "DESCRIBE"]:
                # Queries that return data
                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                rows = cursor.fetchmany(max_rows)

                # Convert to dictionary format
                result_rows = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        value = row[i]
                        # Convert dates and special types to strings
                        if hasattr(value, "isoformat"):
                            value = value.isoformat()
                        row_dict[col] = value
                    result_rows.append(row_dict)

                row_count = len(result_rows)

                result = {
                    "success": True,
                    "sql_type": sql_type,
                    "columns": columns,
                    "rows": result_rows,
                    "row_count": row_count,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }

                yield self.create_json_message(result)
                text_result = self._format_as_markdown_table(result)
                yield self.create_text_message(text_result)
                yield self.create_variable_message("row_count", row_count)
                yield self.create_variable_message("columns", columns)
                yield self.create_variable_message("rows", result_rows)

            elif sql_type in ["INSERT", "UPDATE", "DELETE", "MERGE"]:
                # DML queries - return affected row count
                affected_rows = cursor.rowcount

                result = {
                    "success": True,
                    "columns": [],
                    "rows": [],
                    "row_count": affected_rows,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }

                yield self.create_json_message(result)
                text_result = (
                    f"✅ {sql_type} executed successfully\n"
                    f"📝 Affected rows: {affected_rows}\n"
                    f"⏱️ Execution time: {execution_time:.3f}s"
                )
                yield self.create_text_message(text_result)
                yield self.create_variable_message("row_count", affected_rows)
                yield self.create_variable_message("columns", [])
                yield self.create_variable_message("rows", [])

            elif sql_type in ["CREATE", "DROP", "ALTER", "TRUNCATE"]:
                # DDL queries - execution result only
                result = {
                    "success": True,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }

                yield self.create_json_message(result)
                text_result = (
                    f"✅ {sql_type} statement executed successfully\n"
                    f"⏱️ Execution time: {execution_time:.3f}s"
                )
                yield self.create_text_message(text_result)
                yield self.create_variable_message("row_count", 0)
                yield self.create_variable_message("columns", [])
                yield self.create_variable_message("rows", [])

            else:
                # Other query types
                result = {
                    "success": True,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }

                yield self.create_json_message(result)
                text_result = (
                    f"✅ Query executed successfully\n"
                    f"⏱️ Execution time: {execution_time:.3f}s"
                )
                yield self.create_text_message(text_result)
                yield self.create_variable_message("row_count", 0)
                yield self.create_variable_message("columns", [])
                yield self.create_variable_message("rows", [])

            cursor.close()
            conn.close()

            yield self.create_variable_message("success", True)
            yield self.create_variable_message("executed_sql", sql_query)
            yield self.create_variable_message(
                "execution_time", round(execution_time, 3)
            )

        except snowflake.connector.errors.ProgrammingError as e:
            execution_time = time.time() - start_time
            error_msg = f"❌ SQL Error: {str(e)}"
            yield self.create_text_message(error_msg)
            yield self.create_json_message(
                {
                    "success": False,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                    "error": error_msg,
                }
            )
            yield self.create_variable_message("success", False)
            yield self.create_variable_message("executed_sql", sql_query)
            yield self.create_variable_message(
                "execution_time", round(execution_time, 3)
            )
            yield self.create_variable_message("error", error_msg)

        except snowflake.connector.errors.DatabaseError as e:
            execution_time = time.time() - start_time
            error_msg = f"❌ Database Error: {str(e)}"
            yield self.create_text_message(error_msg)
            yield self.create_json_message(
                {
                    "success": False,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                    "error": error_msg,
                }
            )
            yield self.create_variable_message("success", False)
            yield self.create_variable_message("executed_sql", sql_query)
            yield self.create_variable_message(
                "execution_time", round(execution_time, 3)
            )
            yield self.create_variable_message("error", error_msg)

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"❌ {str(e)}"
            yield self.create_text_message(error_msg)
            yield self.create_json_message(
                {
                    "success": False,
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                    "error": error_msg,
                }
            )
            yield self.create_variable_message("success", False)
            yield self.create_variable_message("executed_sql", sql_query)
            yield self.create_variable_message(
                "execution_time", round(execution_time, 3)
            )
            yield self.create_variable_message("error", error_msg)

    def _format_as_markdown_table(self, result: dict) -> str:
        """
        Format results as markdown table
        """
        if not result.get("success"):
            return f"❌ Error: {result.get('error', 'Unknown error')}"

        sql_type = result.get("sql_type", "QUERY")
        columns = result.get("columns", [])
        rows = result.get("rows", [])
        row_count = result.get("row_count", 0)
        execution_time = result.get("execution_time", 0)

        if not rows:
            return f"✅ {sql_type} executed successfully but returned no results.\n⏱️ Execution time: {execution_time}s"

        # Build markdown table
        text = f"✅ {sql_type} Results ({row_count} rows, {execution_time}s)\n\n"

        # Header row
        text += "| " + " | ".join(columns) + " |\n"

        # Separator row
        text += "| " + " | ".join(["---"] * len(columns)) + " |\n"

        for row in rows[:rows]:
            row_values = [str(row.get(col, "")) for col in columns]
            text += "| " + " | ".join(row_values) + " |\n"

        return text

    def _check_sql_security(self, sql_query: str) -> dict[str, Any]:
        """
        Execute security check on SQL query
        Block dangerous operations
        """
        # Normalize query (uppercase, convert newlines and tabs to spaces)
        normalized_query = sql_query.upper().replace("\n", " ").replace("\t", " ")

        # List of dangerous SQL statements
        dangerous_statements = [
            "GRANT",
            "REVOKE",
            "CREATE USER",
            "DROP USER",
            "ALTER USER",
            "CREATE ROLE",
            "DROP ROLE",
            "ALTER ROLE",
            "CREATE ACCOUNT",
            "DROP ACCOUNT",
            "ALTER ACCOUNT",
            "USE ROLE",
            "USE SECONDARY ROLES",
            "SET SESSION",
            "UNSET SESSION",
            "CREATE SECURITY INTEGRATION",
            "ALTER SECURITY INTEGRATION",
            "DROP SECURITY INTEGRATION",
        ]

        # Check each dangerous statement
        for statement in dangerous_statements:
            # Check if statement has word boundaries before and after
            if f" {statement} " in f" {normalized_query} ":
                return {
                    "allowed": False,
                    "error": f"❌ Security Error: {statement} statements are not allowed for security reasons. "
                    f"This tool is designed for data querying and basic DML operations only. "
                    f"Please contact your database administrator for privilege management.",
                }

        # Check for multiple statements (semicolon-separated queries)
        statements = [stmt.strip() for stmt in sql_query.split(";") if stmt.strip()]
        if len(statements) > 1:
            return {
                "allowed": False,
                "error": "❌ Security Error: Multiple SQL statements in a single query are not allowed. "
                "Please execute one statement at a time for security and clarity.",
            }

        return {"allowed": True, "error": None}
