from collections.abc import Generator
from typing import Any
import sqlite3
import os
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class SelectSQLTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Get the SQL statement
        select_sql = tool_parameters.get("select_sql", "").strip()
        if not select_sql:
            msg = "SELECT SQL statement is required."
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": msg})
            return
        sql_upper = select_sql.upper()
        if not sql_upper.startswith("SELECT"):
            msg = "Only SELECT statements are allowed."
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
                cursor = conn.execute(select_sql)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                row_count = len(rows)
                # Try to extract table name (simple approach)
                table_name = "unknown"
                parts = select_sql.split()
                if "from" in [p.lower() for p in parts]:
                    idx = [p.lower() for p in parts].index("from")
                    if len(parts) > idx + 1:
                        table_name = parts[idx + 1]
                # Format rows as list of dictionaries (standard SQL JSON output)
                formatted_rows = []
                for row in rows:
                    row_dict = {}
                    for i, value in enumerate(row):
                        column_name = columns[i] if i < len(columns) else f"column_{i}"
                        row_dict[column_name] = value
                    formatted_rows.append(row_dict)
                
                # Standard SQL database JSON output format
                sql_result = {
                    "query": select_sql,
                    "table": table_name,
                    "columns": columns,
                    "data": formatted_rows,
                    "row_count": row_count,
                    "status": "success"
                }
                
                # Text message with standard SQL output format
                text_output = f"Table: {table_name}\nColumns: {', '.join(columns)}\nRows: {row_count}\nData: {formatted_rows}"
                
                yield self.create_text_message(text_output)
                yield self.create_json_message(sql_result)
        except sqlite3.OperationalError as e:
            msg = f"SQL error: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": str(e)})
        except Exception as e:
            msg = f"Failed to execute select operation: {e}"
            yield self.create_text_message(msg)
            yield self.create_json_message({"status": "error", "error": str(e)}) 