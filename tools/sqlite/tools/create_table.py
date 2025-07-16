from collections.abc import Generator
from typing import Any
import sqlite3
import os
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class CreateTableTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Get the SQL statement
        create_table_sql = tool_parameters.get("create_table_sql", "").strip()
        if not create_table_sql:
            msg = "CREATE TABLE SQL statement is required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not create_table_sql.upper().startswith("CREATE TABLE"):
            msg = "Only CREATE TABLE statements are allowed."
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
                conn.execute(create_table_sql)
                conn.commit()
                # Extract table name (simple approach)
                table_name = create_table_sql.split()[2]
                cursor = conn.execute(f"PRAGMA table_info({table_name})")
                columns = [{"name": row[1], "type": row[2]} for row in cursor.fetchall()]
                col_list = ", ".join([f"{col['name']} {col['type']}" for col in columns])
                summary = f"Table {table_name} created successfully with columns: {col_list}"
                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "status": "success",
                    "message": summary,
                    "table": table_name,
                    "columns": columns
                })
        except sqlite3.OperationalError as e:
            yield self.create_text_message(f"SQL error: {e}")
            yield self.create_json_message({"status": "error", "error": str(e)})
        except Exception as e:
            yield self.create_text_message(f"Failed to create table: {e}")
            yield self.create_json_message({"status": "error", "error": str(e)})
