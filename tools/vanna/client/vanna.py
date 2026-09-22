import json
import re
from io import StringIO
from typing import Any

import httpx2
import pandas as pd
import sqlparse
from pydantic import BaseModel

DEFAULT_ENDPOINT = "https://ask.vanna.ai/rpc"


class TextResult(BaseModel):
    data: str


class Status(BaseModel):
    success: bool
    message: str = ""


class TrainingData(BaseModel):
    questions: list[dict[str, Any] | None]
    ddl: list[str]
    documentation: list[str]


class Models(BaseModel):
    organizations: list[str]


class VannaClient:
    """The RPC operations used by the Dify plugin, without the Vanna SDK."""

    def __init__(
        self, http: httpx2.Client, api_key: str, model: str = "", endpoint: str | None = None
    ):
        self.http = http
        url = httpx2.URL(endpoint or DEFAULT_ENDPOINT)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("Vanna endpoint must be an HTTP or HTTPS URL")
        self.endpoint = url
        self.headers = {"Vanna-Key": api_key, "Vanna-Org": model}

    def call[T: BaseModel](
        self, method: str, params: list[dict[str, Any]], result_type: type[T]
    ) -> T:
        request = self.http.build_request(
            "POST", self.endpoint, headers=self.headers, json={"method": method, "params": params}
        )
        for _ in range(6):
            response = self.http.send(request, follow_redirects=False)
            redirect = response.next_request
            if redirect is None:
                break
            if (redirect.url.scheme, redirect.url.host, redirect.url.port) != (
                self.endpoint.scheme,
                self.endpoint.host,
                self.endpoint.port,
            ):
                raise ValueError(
                    "Vanna endpoint redirected to a different origin; configure its final URL"
                )
            request = redirect
        else:
            raise ValueError("Too many Vanna endpoint redirects")
        response.raise_for_status()
        envelope = response.json()
        if (
            not isinstance(envelope, dict)
            or envelope.get("error")
            or envelope.get("result") is None
        ):
            raise ValueError(f"Vanna RPC {method} failed: missing result or server error")
        result = result_type.model_validate(envelope["result"])
        if isinstance(result, Status) and not result.success:
            raise ValueError(f"Vanna RPC {method} failed: {result.message}")
        return result

    def validate_credentials(self) -> None:
        self.call("list_my_models", [], Models)

    def related_training(self, question: str) -> TrainingData:
        return self.call("get_related_training_data", [{"question": question}], TrainingData)

    def submit_prompt(self, messages: list[dict[str, str]]) -> str:
        return self.call(
            "submit_prompt", [{"data": json.dumps(messages, ensure_ascii=False)}], TextResult
        ).data

    def training_data(self) -> pd.DataFrame:
        data = self.call("get_training_data", [], TextResult).data
        return pd.read_json(StringIO(data))

    def remove_training(self, training_id: str) -> None:
        self.call("remove_training_data", [{"data": training_id}], Status)

    def add_ddl(self, ddl: str) -> None:
        self.call("add_ddl", [{"data": ddl}], Status)

    def add_documentation(self, documentation: str) -> None:
        self.call("add_documentation", [{"data": documentation}], Status)

    def add_sql(self, question: str, sql: str) -> None:
        self.call(
            "add_sql", [{"question": question, "sql": sql, "tag": "Manually Trained"}], Status
        )

    def question_for_sql(self, sql: str) -> str:
        return self.submit_prompt(
            [
                {
                    "role": "system",
                    "content": (
                        "The user will give you SQL and you will try to guess what the business question "
                        "this query is answering. Return just the question without any additional explanation. "
                        "Do not reference the table name in the question."
                    ),
                },
                {"role": "user", "content": sql},
            ]
        )


def sql_prompt(question: str, dialect: str, training: TrainingData) -> list[dict[str, str]]:
    # Preserve the legacy service's prompt contract; see LICENSE.vanna.
    prompt = (
        f"You are a {dialect} expert. "
        "Please help to generate a SQL query to answer the question. Your response should ONLY be "
        "based on the given context and follow the response guidelines and format instructions. "
    )
    for heading, documents in (
        ("\n===Tables \n", training.ddl),
        ("\n===Additional Context \n\n", training.documentation),
    ):
        if documents:
            prompt += heading
            for document in documents:
                if len(prompt) + len(document) < 14000 * 4:
                    prompt += f"{document}\n\n"
    prompt += (
        "===Response Guidelines \n"
        "1. If the provided context is sufficient, please generate a valid SQL query without any "
        "explanations for the question. \n"
        "2. If the provided context is almost sufficient but requires knowledge of a specific string "
        "in a particular column, please generate an intermediate SQL query to find the distinct strings "
        "in that column. Prepend the query with a comment saying intermediate_sql \n"
        "3. If the provided context is insufficient, please explain why it can't be generated. \n"
        "4. Please use the most relevant table(s). \n"
        "5. If the question has been asked and answered before, please repeat the answer exactly as "
        "it was given before. \n"
        f"6. Ensure that the output SQL is {dialect}-compliant and executable, and free of syntax errors. \n"
    )
    messages = [{"role": "system", "content": prompt}]
    for example in training.questions:
        if (
            example
            and isinstance(example.get("question"), str)
            and isinstance(example.get("sql"), str)
        ):
            messages.extend(
                [
                    {"role": "user", "content": example["question"]},
                    {"role": "assistant", "content": example["sql"]},
                ]
            )
    return messages + [{"role": "user", "content": question}]


def extract_sql(response: str) -> str:
    # Prefer fenced/raw SQL so semicolons in string literals do not truncate it.
    blocks = re.findall(r"```(?:sql\s*)?\n?(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if blocks:
        statements = sqlparse.split(blocks[-1])
        if not statements:
            raise ValueError("Vanna returned an empty SQL block")
        return statements[0]
    if re.match(
        r"\s*(?:--[^\n]*\n\s*)*(?:WITH|SELECT|CREATE|INSERT|UPDATE|DELETE)\b",
        response,
        re.IGNORECASE,
    ):
        return sqlparse.split(response)[0]
    for pattern in (r"\bCREATE\s+TABLE\b.*?\bAS\b", r"\bWITH\b\s", r"\bSELECT\b\s"):
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            candidate = sqlparse.split(response[match.start() :])[0]
            if looks_like_sql(candidate):
                return candidate
    return sqlparse.split(response)[0] if looks_like_sql(response) else response.strip()


def looks_like_sql(text: str) -> bool:
    """Distinguish a model's explanation from SQL, not an SQL authorization check."""
    statements = sqlparse.parse(text)
    if not statements:
        return False
    statement = statements[0]
    first = statement.token_first(skip_cm=True)
    return statement.get_type() != "UNKNOWN" or (
        first is not None
        and first.normalized.split()[0]
        in {
            "SHOW",
            "DESCRIBE",
            "DESC",
            "EXPLAIN",
            "PRAGMA",
            "VALUES",
            "TABLE",
            "CALL",
            "EXEC",
            "EXECUTE",
            "SET",
            "USE",
        }
    )


def metadata_documents(frame: pd.DataFrame) -> list[str]:
    """Group INFORMATION_SCHEMA columns without evaluating database identifiers."""
    names = {str(column).lower(): column for column in frame.columns}
    catalog = next(
        (column for name, column in names.items() if "database" in name or "table_catalog" in name),
        None,
    )
    schema = next((column for name, column in names.items() if "table_schema" in name), None)
    table = next((column for name, column in names.items() if "table_name" in name), None)
    if catalog is None or schema is None or table is None:
        raise ValueError("Database metadata must include catalog, schema and table columns")
    columns = [catalog, schema, table] + [
        column
        for name, column in names.items()
        if any(part in name for part in ("column_name", "data_type", "comment"))
    ]
    return [
        f"The following columns are in the {table_name} table in the {database} database:\n\n"
        + group[columns].to_markdown()
        for (database, _, table_name), group in frame.groupby(
            [catalog, schema, table], sort=False, dropna=False
        )
    ]
