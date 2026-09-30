from collections.abc import Generator
from typing import Any, Literal

import httpx2
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from pydantic import BaseModel, ConfigDict, Field

from client.database import connect_database
from client.vanna import VannaClient, extract_sql, looks_like_sql, metadata_documents, sql_prompt


class Parameters(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    url: str = Field(min_length=1)
    db_type: Literal[
        "SQLite", "Postgres", "DuckDB", "SQLServer", "MySQL", "Oracle", "Hive", "ClickHouse"
    ] = "SQLite"
    db_name: str = ""
    username: str = ""
    password: str = ""
    port: int = Field(default=0, ge=0, le=65535)
    ddl: str = ""
    question: str = ""
    sql: str = ""
    memos: str = ""
    enable_training: bool = False
    reset_training_data: bool = False
    training_metadata: bool = False
    allow_llm_to_see_data: bool = False


class VannaTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        api_key = self.runtime.credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("Please input api key")
        params = Parameters.model_validate(
            {key: value for key, value in tool_parameters.items() if value is not None}
        )
        if params.db_type in {"Postgres", "MySQL", "Hive", "ClickHouse"} and (
            not params.db_name or not params.username or not params.port
        ):
            raise ValueError("Please input database name, username and port")

        with httpx2.Client(timeout=httpx2.Timeout(120, connect=10)) as http:
            client = VannaClient(
                http, api_key, params.model, self.runtime.credentials.get("base_url")
            )
            with connect_database(params.model_dump(), http) as database:
                if params.enable_training:
                    if params.reset_training_data:
                        existing = client.training_data()
                        if not existing.empty:
                            for training_id in existing["id"]:
                                client.remove_training(str(training_id))
                    if params.training_metadata:
                        if params.db_type == "SQLite":
                            schema = database.run_sql(
                                "SELECT type, sql FROM sqlite_master WHERE sql is not null"
                            )
                            for ddl in schema["sql"]:
                                client.add_ddl(ddl)
                        else:
                            schema = database.run_sql("SELECT * FROM INFORMATION_SCHEMA.COLUMNS")
                            for document in metadata_documents(schema):
                                client.add_documentation(document)
                    if params.ddl:
                        client.add_ddl(params.ddl)
                    if params.sql:
                        question = params.question or client.question_for_sql(params.sql)
                        client.add_sql(question, params.sql)
                    if params.memos:
                        client.add_documentation(params.memos)

                training = client.related_training(params.prompt)
                response = client.submit_prompt(
                    sql_prompt(params.prompt, database.dialect, training)
                )
                if "intermediate_sql" in response:
                    if not params.allow_llm_to_see_data:
                        yield self.create_text_message(
                            "The LLM is not allowed to see the data in your database. Your question requires "
                            "database introspection to generate the necessary SQL. Please set "
                            "allow_llm_to_see_data=True to enable this."
                        )
                        return
                    intermediate_sql = extract_sql(response)
                    if not looks_like_sql(intermediate_sql):
                        yield self.create_text_message(response)
                        return
                    intermediate = database.run_sql(intermediate_sql)
                    training.documentation.append(
                        f"The following is a pandas DataFrame with the results of the intermediate SQL query "
                        f"{intermediate_sql}: \n" + intermediate.to_markdown()
                    )
                    response = client.submit_prompt(
                        sql_prompt(params.prompt, database.dialect, training)
                    )

                sql = extract_sql(response)
                yield self.create_text_message(sql)
                if not looks_like_sql(sql):
                    return
                result = database.run_sql(sql)
                if not result.empty:
                    client.add_sql(params.prompt, sql)
                yield self.create_text_message(result.to_markdown())
