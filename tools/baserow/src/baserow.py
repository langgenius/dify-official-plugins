import json
from typing import Annotated, Generator

from baserowapi import Baserow
from pydantic import BaseModel

from .model import (
    BasePlugin,
    Credential,
    CredentialType,
    MetaInfo,
    Param,
    ParamType,
    provider,
    tool,
)


class BaserowCredentials(BaseModel):
    url: Annotated[
        str,
        Credential(
            name="url",
            label="Baserow API URL",
            placeholder="https://api.baserow.io",
            help="The base URL for the Baserow API.",
            type=CredentialType.text_input,
            required=True,
            url="",
        ),
    ] = "https://api.baserow.io"
    token: Annotated[
        str,
        Credential(
            name="token",
            label="Baserow API Token",
            placeholder="",
            help="Your Baserow API token for authentication.",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""


class BaserowPlugin(BasePlugin):

    credentials: BaserowCredentials = BaserowCredentials()

    @tool(
        name="get_tables",
        label="Get Tables",
        description="Retrieve all tables from Baserow",
    )
    def get_tables(self) -> Generator:
        baserow = Baserow(url=self.credentials.url, token=self.credentials.token)
        res: list = baserow.make_api_request("/api/database/tables/all-tables/")

        yield res
        yield str(res)

    @tool(
        name="get_rows",
        label="Get Rows",
        description="Retrieve rows from a Baserow table.",
    )
    def get_rows(
        self,
        table_id: Annotated[
            int,
            Param(
                name="table_id",
                label="Table ID",
                description="The ID of the table to retrieve rows from.",
                type=ParamType.number,
                required=True,
                form="schema",
            ),
        ],
    ) -> Generator:
        baserow = Baserow(url=self.credentials.url, token=self.credentials.token)
        table = baserow.get_table(table_id)
        rows = table.get_rows()

        rows_list = [row.to_dict() for row in rows]

        yield rows_list
        yield str(rows_list)

    @tool(
        name="get_a_row",
        label="Get a Row",
        description="Retrieve a specific row from a Baserow table by its ID.",
    )
    def get_a_row(
        self,
        row_id: Annotated[
            int,
            Param(
                name="row_id",
                label="Row ID",
                description="The ID of the row to retrieve.",
                type=ParamType.number,
                required=True,
            ),
        ],
        table_id: Annotated[
            int,
            Param(
                name="table_id",
                label="Table ID",
                description="The ID of the table to retrieve the row from.",
                type=ParamType.number,
                required=True,
                form="schema",
            ),
        ],
    ) -> Generator:
        baserow = Baserow(url=self.credentials.url, token=self.credentials.token)
        table = baserow.get_table(table_id)
        row = table.get_row(row_id)

        yield row.to_dict()
        yield str(row.to_dict())

    @tool(
        name="create_a_row",
        label="Create a Row",
        description="Create a new row in a Baserow table.",
    )
    def create_a_row(
        self,
        table_id: Annotated[
            int,
            Param(
                name="table_id",
                label="Table ID",
                description="The ID of the table to create the row in.",
                type=ParamType.number,
                required=True,
                form="schema",
            ),
        ],
        content: Annotated[
            str,
            Param(
                name="content",
                label="Content",
                description="The content of the row to create.",
                type=ParamType.string,
                required=True,
                form="llm",
            ),
        ],
    ) -> Generator:
        baserow = Baserow(url=self.credentials.url, token=self.credentials.token)
        table = baserow.get_table(table_id)
        new_row = table.add_rows(json.loads(content))

        assert len(new_row) == 1, "Failed to create a new row."

        yield new_row[0].to_dict()
        yield str(new_row[0].to_dict())

    @tool(
        name="update_a_row",
        label="Update a Row",
        description="Update an existing row in a Baserow table.",
    )
    def update_a_row(
        self,
        table_id: Annotated[
            int,
            Param(
                name="table_id",
                label="Table ID",
                description="The ID of the table to update the row in.",
                type=ParamType.number,
                required=True,
                form="schema",
            ),
        ],
        row_id: Annotated[
            int,
            Param(
                name="row_id",
                label="Row ID",
                description="The ID of the row to update.",
                type=ParamType.number,
                required=True,
            ),
        ],
        content: Annotated[
            str,
            Param(
                name="content",
                label="Content",
                description="The content of the row to update.",
                type=ParamType.string,
                required=True,
                form="llm",
            ),
        ],
    ) -> Generator:
        baserow = Baserow(url=self.credentials.url, token=self.credentials.token)
        table = baserow.get_table(table_id)

        try:
            row = table.get_row(row_id)
        except Exception as e:
            raise ValueError(
                f"Row with ID {row_id} not found in table {table_id}."
            ) from e

        updated_rows = table.update_rows([{"id": row_id, **json.loads(content)}])
        assert len(updated_rows) == 1, "Failed to update the row."

        yield updated_rows[0].to_dict()
        yield str(updated_rows[0].to_dict())

    @provider
    def verify(self):
        baserow = Baserow(url=self.credentials.url, token=self.credentials.token)

        _ = baserow.make_api_request(endpoint="/api/database/tables/all-tables/")


plugin = BaserowPlugin(
    meta=MetaInfo(
        name="baserow",
        version="0.0.1",
        label="Baserow",
        author="langgenius",
        description="Baserow plugin for managing rows in a Baserow table.",
    ),
)
