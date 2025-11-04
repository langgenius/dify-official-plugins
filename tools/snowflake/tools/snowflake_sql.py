import re
import time
from typing import Any, Generator

import snowflake.connector
import sqlparse
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from sqlparse import tokens


class SnowflakeQueryTool(Tool):
    def _parse_sql_with_sqlparse(self, sql_query: str) -> tuple[bool, str, list]:
        """
        SQLクエリをパースして構文を検証

        Returns:
            (is_valid, error_message, statements)
        """
        try:
            # SQLをパース
            parsed = sqlparse.parse(sql_query)

            if not parsed:
                return False, "Failed to parse SQL query", []

            statements = []
            for statement in parsed:
                # 空の文をスキップ
                if statement.ttype is None and str(statement).strip():
                    statements.append(statement)

            if len(statements) == 0:
                return False, "No valid SQL statements found", []

            if len(statements) > 1:
                return False, "Multiple SQL statements detected", statements

            # 単一のステートメントを詳細検証
            statement = statements[0]

            # 基本的な構文エラー検出
            sql_text = str(statement).strip()
            syntax_error = self._check_basic_syntax_errors(sql_text)
            if syntax_error:
                return False, syntax_error, statements

            # 危険なトークンの検出
            dangerous_tokens = self._check_dangerous_tokens(statement)
            if dangerous_tokens:
                return (
                    False,
                    f"Dangerous SQL tokens detected: {', '.join(dangerous_tokens)}",
                    statements,
                )

            return True, "", statements

        except Exception as e:
            return False, f"SQL parsing error: {str(e)}", []

    def _check_basic_syntax_errors(self, sql_text: str) -> str:
        """
        基本的な構文エラーを検出
        """
        sql_upper = sql_text.upper().strip()

        # SELECT文の基本チェック
        if sql_upper.startswith("SELECT"):
            if "FROM WHERE" in sql_upper:
                return "Invalid SQL syntax: FROM WHERE without table name"
            if "SELECT FROM" in sql_upper:
                return "Invalid SQL syntax: SELECT FROM without columns"

        # 一般的な構文エラーパターン
        error_patterns = [
            (r"\bFROM\s+WHERE\b", "Missing table name between FROM and WHERE"),
            (r"\bSELECT\s+FROM\b", "Missing column list between SELECT and FROM"),
            (r"\bINSERT\s+VALUES\b", "Missing INTO clause in INSERT statement"),
            (
                r"\bUPDATE\s+SET\s+WHERE\b",
                "Missing column assignment in UPDATE statement",
            ),
        ]

        for pattern, error_msg in error_patterns:
            if re.search(pattern, sql_upper):
                return f"SQL syntax error: {error_msg}"

        return ""

    def _check_dangerous_tokens(self, statement) -> list[str]:
        """
        パースされたSQLステートメントから危険なトークンを検出
        """
        dangerous_found = []

        # 危険なキーワードパターン
        dangerous_patterns = {
            "SYSTEM$": r"SYSTEM\$",
            "EXTERNAL_FUNCTION": r"EXTERNAL\s+FUNCTION",
            "EXTERNAL_TABLE": r"EXTERNAL\s+TABLE",
            "CREATE_FUNCTION": r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?FUNCTION",
            "CREATE_PROCEDURE": r"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE",
            "GRANT_REVOKE": r"\b(?:GRANT|REVOKE)\b",
            "FILE_OPERATIONS": r"\b(?:GET|PUT|LS|RM)\s+@",
            "SESSION_MANAGEMENT": r"\b(?:KILL\s+SESSION|ALTER\s+SESSION)\b",
        }

        # ステートメントを文字列に変換して検査
        sql_text = str(statement).upper()

        for pattern_name, pattern in dangerous_patterns.items():
            if re.search(pattern, sql_text, re.IGNORECASE):
                dangerous_found.append(pattern_name)

        # トークン単位でより詳細にチェック
        self._recursive_token_check(statement, dangerous_found)

        return dangerous_found

    def _recursive_token_check(self, token, dangerous_found: list):
        """
        再帰的にトークンをチェックして危険なパターンを検出
        """
        if hasattr(token, "tokens"):
            for sub_token in token.tokens:
                self._recursive_token_check(sub_token, dangerous_found)

        # キーワードトークンをチェック
        if token.ttype is tokens.Keyword:
            keyword = str(token).upper().strip()

            # 危険なキーワードのリスト
            dangerous_keywords = [
                "SYSTEM$",
                "GRANT",
                "REVOKE",
                "CREATE ROLE",
                "DROP ROLE",
                "CREATE USER",
                "DROP USER",
                "ALTER USER",
                "ALTER ACCOUNT",
                "KILL",
                "EXTERNAL",
            ]

            for dangerous_keyword in dangerous_keywords:
                if (
                    dangerous_keyword in keyword
                    and dangerous_keyword not in dangerous_found
                ):
                    dangerous_found.append(
                        f"KEYWORD_{dangerous_keyword.replace(' ', '_')}"
                    )

    def _validate_sql_structure(
        self, statements: list, declared_sql_type: str
    ) -> tuple[bool, str]:
        """
        パースされたSQLの構造を検証
        """
        if not statements:
            return False, "No statements to validate"

        statement = statements[0]

        # ステートメントの最初の意味のあるキーワードを取得
        first_keyword = None
        for token in statement.flatten():
            if token.ttype is tokens.Keyword:
                keyword = str(token).upper().strip()
                # 空白やコメントではない最初のキーワードを取得
                if keyword and keyword not in ["", " ", "\n", "\t"]:
                    first_keyword = keyword
                    break
            elif token.ttype is tokens.Keyword.DML:
                # DMLキーワード（SELECT, INSERT, UPDATE, DELETE）
                first_keyword = str(token).upper().strip()
                break

        if not first_keyword:
            # トークンベースで取得できない場合、文字列ベースで取得
            sql_text = str(statement).strip().upper()
            words = sql_text.split()
            if words:
                first_keyword = words[0]

        if not first_keyword:
            return False, "Could not determine SQL statement type"

        # 文字列ベースでのSQL種別検出（WITH句対応）
        sql_text = str(statement).upper().strip()

        # WITH句の特別処理
        if sql_text.startswith("WITH"):
            # WITH句の場合、実際のメインクエリを探す
            if declared_sql_type == "SELECT":
                if "SELECT" not in sql_text:
                    return False, "WITH clause declared as SELECT but no SELECT found"
            elif declared_sql_type in ["INSERT", "UPDATE", "DELETE", "MERGE"]:
                if declared_sql_type not in sql_text:
                    return (
                        False,
                        f"WITH clause declared as {declared_sql_type} but no {declared_sql_type} found",
                    )
            # WITH句の場合は正常
            return True, ""
        else:
            # 通常のクエリの型チェック
            expected_keywords = {
                "SELECT": ["SELECT"],
                "INSERT": ["INSERT"],
                "UPDATE": ["UPDATE"],
                "DELETE": ["DELETE"],
                "MERGE": ["MERGE"],
                "CREATE": ["CREATE"],
                "DROP": ["DROP"],
                "ALTER": ["ALTER"],
                "TRUNCATE": ["TRUNCATE"],
                "SHOW": ["SHOW"],
                "DESCRIBE": ["DESCRIBE", "DESC"],
                "OTHER": [],
            }

            if declared_sql_type != "OTHER":
                expected = expected_keywords.get(declared_sql_type, [])
                if expected and first_keyword not in expected:
                    return (
                        False,
                        f"SQL type mismatch: declared as {declared_sql_type} but detected as {first_keyword}",
                    )

        return True, ""

    def _validate_sql_query(
        self, sql_query: str, declared_sql_type: str
    ) -> tuple[bool, str]:
        """
        SQLクエリのセキュリティ検証を行う（SQLパーサー使用）

        Returns:
            (is_valid, error_message)
        """
        if not sql_query or not sql_query.strip():
            return False, "SQL query cannot be empty"

        # 基本的な長さ制限
        if len(sql_query) > 10000:  # 10KB制限
            return False, "SQL query is too long (max 10,000 characters)"

        # 1. SQLパーサーによる構文解析
        parse_valid, parse_error, statements = self._parse_sql_with_sqlparse(sql_query)
        if not parse_valid:
            return False, f"SQL parsing failed: {parse_error}"

        # 2. 構造検証（SQL型の整合性チェック）
        structure_valid, structure_error = self._validate_sql_structure(
            statements, declared_sql_type
        )
        if not structure_valid:
            return False, f"SQL structure validation failed: {structure_error}"

        # 3. 従来の正規表現ベースの追加検証（補完的）
        regex_valid, regex_error = self._validate_with_regex_patterns(
            sql_query, declared_sql_type
        )
        if not regex_valid:
            return False, regex_error

        return True, ""

    def _validate_with_regex_patterns(
        self, sql_query: str, declared_sql_type: str
    ) -> tuple[bool, str]:
        """
        正規表現ベースの追加セキュリティ検証（パーサーの補完）
        """
        sql_upper = sql_query.upper()

        # SQLインジェクション攻撃パターンの検出
        injection_patterns = [
            (r"\bOR\s+1\s*=\s*1\b", "SQL injection detected: OR 1=1 pattern"),
            (
                r"\bOR\s+['\"]\s*['\"]\s*=\s*['\"]\s*['\"]",
                "SQL injection detected: OR ''='' pattern",
            ),
            (r"\bAND\s+1\s*=\s*1\b", "SQL injection detected: AND 1=1 pattern"),
            (
                r"\bUNION\s+(?:ALL\s+)?SELECT",
                "SQL injection detected: UNION SELECT attack",
            ),
            (r";\s*DROP\s+", "SQL injection detected: DROP statement injection"),
            (r";\s*DELETE\s+", "SQL injection detected: DELETE statement injection"),
            (r";\s*INSERT\s+", "SQL injection detected: INSERT statement injection"),
            (r";\s*UPDATE\s+", "SQL injection detected: UPDATE statement injection"),
            (r"--\s*$", "SQL injection detected: Comment-based injection"),
            (r"/\*.*\*/", "SQL injection detected: Block comment injection"),
            (
                r"\bOR\s+[0-9]+\s*=\s*[0-9]+",
                "SQL injection detected: OR numeric comparison",
            ),
            (
                r"\bAND\s+[0-9]+\s*=\s*[0-9]+",
                "SQL injection detected: AND numeric comparison",
            ),
        ]

        for pattern, message in injection_patterns:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                return False, message

        # 特に危険なパターン（パーサーでキャッチしにくいもの）
        critical_patterns = [
            (r"\bSYSTEM\$[A-Z_]+\s*\(", "System function calls are prohibited"),
            (
                r"@[A-Z_][A-Z0-9_]*(?:/|\s)",
                "Stage references may be restricted",
            ),  # ステージ参照を正確に検出
            (r"\bCALL\s+SYSTEM\$", "System procedure calls are prohibited"),
            (
                r"\bSET\s+[A-Z_]+=.*\(",
                "Dynamic parameter setting with functions may be dangerous",
            ),
            (r"javascript:", "JavaScript code injection detected"),
            (r"<script", "Script injection detected"),
        ]

        for pattern, message in critical_patterns:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                return False, message

        # DDL操作の追加制限
        if declared_sql_type in ["CREATE", "DROP", "ALTER"]:
            restricted_ddl_patterns = [
                (
                    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?USER\b",
                    "User management operations are restricted",
                ),
                (
                    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?ROLE\b",
                    "Role management operations are restricted",
                ),
                (
                    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?WAREHOUSE\b",
                    "Warehouse management operations are restricted",
                ),
                (
                    r"\bALTER\s+ACCOUNT\b",
                    "Account modification operations are restricted",
                ),
                (
                    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?NETWORK\s+POLICY\b",
                    "Network policy operations are restricted",
                ),
            ]

            for pattern, message in restricted_ddl_patterns:
                if re.search(pattern, sql_upper, re.IGNORECASE):
                    return False, message

        return True, ""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Execute SQL query on Snowflake database using OAuth authentication.
        """
        sql_query = tool_parameters.get("sql_query", "")
        sql_type = tool_parameters.get("sql_type", "SELECT").upper()
        max_rows = tool_parameters.get("max_rows", 100)

        # SQLクエリの検証
        is_valid, error_message = self._validate_sql_query(sql_query, sql_type)
        if not is_valid:
            yield self.create_text_message(f"❌ Security Error: {error_message}")
            yield self.create_json_message(
                {
                    "success": False,
                    "error": f"Security validation failed: {error_message}",
                    "sql_type": sql_type,
                    "executed_sql": sql_query,
                    "execution_time": 0,
                }
            )
            yield self.create_variable_message("success", False)
            yield self.create_variable_message("error", error_message)
            return

        # 認証情報の取得
        account_name = self.runtime.credentials.get("account_name")
        access_token = self.runtime.credentials.get("access_token")
        warehouse = tool_parameters.get("warehouse") or self.runtime.credentials.get(
            "warehouse",
        )
        database = tool_parameters.get("database") or self.runtime.credentials.get(
            "database"
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
