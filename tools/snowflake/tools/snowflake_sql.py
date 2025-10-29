import logging
import time
from typing import Any, Generator

import snowflake.connector
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


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

        # 認証情報の取得
        account_name = self.runtime.credentials.get("account_name")
        access_token = self.runtime.credentials.get("access_token")
        warehouse = tool_parameters.get("warehouse") or self.runtime.credentials.get(
            "warehouse", "COMPUTE_WH"
        )
        database = tool_parameters.get("database") or self.runtime.credentials.get(
            "database", "OAUTH_TEST_DB"
        )
        schema = tool_parameters.get("schema") or self.runtime.credentials.get(
            "schema", "PUBLIC"
        )

        start_time = time.time()

        try:
            # OAuth認証での接続
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

            # SQLの種類に応じて結果を処理
            if sql_type in ["SELECT", "SHOW", "DESCRIBE"]:
                # データを返すクエリ
                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                rows = cursor.fetchmany(max_rows)

                # 辞書形式に変換
                result_rows = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        value = row[i]
                        # 日付や特殊型を文字列に変換
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
                # DMLクエリ - 影響を受けた行数を返す
                affected_rows = cursor.rowcount

                result = {
                    "success": True,
                    "sql_type": sql_type,
                    "affected_rows": affected_rows,
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
                yield self.create_variable_message("row_count", len(affected_rows))
                yield self.create_variable_message("columns", [])
                yield self.create_variable_message("rows", affected_rows)

            elif sql_type in ["CREATE", "DROP", "ALTER", "TRUNCATE"]:
                # DDLクエリ - 実行結果のみ
                result = {
                    "success": True,
                    "sql_type": sql_type,
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
                # その他のクエリ
                result = {
                    "success": True,
                    "sql_type": sql_type,
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
                    "sql_type": sql_type,
                    "error": error_msg,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }
            )
            logger.error(error_msg)
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
                    "sql_type": sql_type,
                    "error": error_msg,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }
            )
            logger.error(error_msg)
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
                    "sql_type": sql_type,
                    "error": error_msg,
                    "executed_sql": sql_query,
                    "execution_time": round(execution_time, 3),
                }
            )
            logger.error(error_msg)
            yield self.create_variable_message("success", False)
            yield self.create_variable_message("executed_sql", sql_query)
            yield self.create_variable_message(
                "execution_time", round(execution_time, 3)
            )
            yield self.create_variable_message("error", error_msg)

    def _format_as_markdown_table(self, result: dict) -> str:
        """
        結果をマークダウンテーブル形式にフォーマット
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

        # マークダウンテーブルを構築
        text = f"✅ {sql_type} Results ({row_count} rows, {execution_time}s)\n\n"

        # ヘッダー行
        text += "| " + " | ".join(columns) + " |\n"

        # セパレーター行
        text += "| " + " | ".join(["---"] * len(columns)) + " |\n"

        # データ行（最大20行まで）
        display_limit = min(20, len(rows))
        for row in rows[:display_limit]:
            row_values = [str(row.get(col, "")) for col in columns]
            text += "| " + " | ".join(row_values) + " |\n"

        # 残りの行数を表示
        if row_count > display_limit:
            text += f"\n... and {row_count - display_limit} more rows (use LIMIT to reduce results)\n"

        return text
