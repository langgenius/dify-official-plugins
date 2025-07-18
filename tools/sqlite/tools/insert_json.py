from collections.abc import Generator
from typing import Any
import sqlite3
import os
import json
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class InsertJSONTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        table = tool_parameters.get("table", "").strip()
        data_str = tool_parameters.get("data", "")
        if not table:
            msg = "Table name is required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not data_str:
            msg = "Data to insert is required."
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
        # Normalize data to a list of dicts
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            msg = "Data must be a JSON object or a list of JSON objects."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        if not data:
            msg = "No data provided for insert."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        columns = list(data[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        column_names = ", ".join(columns)
        sql = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
        values = [tuple(row.get(col) for col in columns) for row in data]
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
                cursor = conn.executemany(sql, values)
                conn.commit()
                row_count = cursor.rowcount
                msg = f"{row_count} row(s) inserted into table {table}."
                yield self.create_text_message(msg)
                yield self.create_json_message({
                    "status": "success",
                    "message": msg,
                    "table": table,
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