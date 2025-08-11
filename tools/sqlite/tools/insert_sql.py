from collections.abc import Generator
from typing import Any
import sqlite3
import os
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class InsertSQLTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Get the SQL statement
        insert_sql = tool_parameters.get("insert_sql", "").strip()
        if not insert_sql:
            msg = "INSERT SQL statement is required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        sql_upper = insert_sql.upper()
        if not sql_upper.startswith("INSERT"):
            msg = "Only INSERT statements are allowed."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        # Get database path from credentials
        database_path = self.runtime.credentials.get("database_path")
        if not database_path:
            msg = "Database file path is required in credentials."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not os.path.isfile(database_path):
            msg = f"Database file does not exist: {database_path}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        try:
            with sqlite3.connect(database_path) as conn:
                cursor = conn.execute(insert_sql)
                conn.commit()
                # Extract table name (simple approach)
                parts = insert_sql.split()
                table_name = parts[2] if len(parts) > 2 else "unknown"
                row_count = cursor.rowcount
                msg = f"{row_count} row(s) inserted into table {table_name}."
                yield self.create_text_message(msg)
                yield self.create_json_message({
                    "status": "success",
                    "message": msg,
                    "table": table_name,
                    "rows_inserted": row_count
                })
        except sqlite3.OperationalError as e:
            msg = f"SQL error: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": str(e)})
        except Exception as e:
            msg = f"Failed to execute insert operation: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": str(e)}) 