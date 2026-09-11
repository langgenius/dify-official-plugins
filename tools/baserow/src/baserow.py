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
        table = baserow.get_table(int(table_id))
        rows = table.get_rows()

        rows_list = [dict(row.raw_values) for row in rows]

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
        table = baserow.get_table(int(table_id))
        row = table.get_row(row_id)

        yield dict(row.raw_values)
        yield str(dict(row.raw_values))

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
        table = baserow.get_table(int(table_id))
        new_row = table.add_row(json.loads(content))

        yield dict(new_row.raw_values)
        yield str(dict(new_row.raw_values))

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
        table = baserow.get_table(int(table_id))
        updated_row = table.update_row(row_id, json.loads(content))

        yield dict(updated_row.raw_values)
        yield str(dict(updated_row.raw_values))

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
