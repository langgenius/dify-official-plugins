from collections.abc import Generator
from typing import Any
import sqlite3
import os
import json
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class UpdateJSONTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        table = tool_parameters.get("table", "").strip()
        data_str = tool_parameters.get("data", "")
        where_str = tool_parameters.get("where", "")
        if not table:
            msg = "Table name is required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not data_str:
            msg = "Data to update is required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not where_str:
            msg = "Where conditions are required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        try:
            data = json.loads(data_str)
        except Exception as e:
            msg = f"Invalid JSON for data: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        try:
            where = json.loads(where_str)
        except Exception as e:
            msg = f"Invalid JSON for where: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not isinstance(data, dict):
            msg = "Data to update must be a JSON object."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not isinstance(where, dict):
            msg = "Where conditions must be a JSON object."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        set_clause = ", ".join([f"{col} = ?" for col in data.keys()])
        where_clause = " AND ".join([f"{col} = ?" for col in where.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        values = list(data.values()) + list(where.values())
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
                cursor = conn.execute(sql, values)
                conn.commit()
                row_count = cursor.rowcount
                msg = f"{row_count} row(s) updated in table {table}."
                yield self.create_text_message(msg)
                yield self.create_json_message({
                    "status": "success",
                    "message": msg,
                    "table": table,
                    "rows_updated": row_count
                })
        except sqlite3.OperationalError as e:
            msg = f"SQL error: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": str(e)})
        except Exception as e:
            msg = f"Failed to execute update operation: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": str(e)}) 