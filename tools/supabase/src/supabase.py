import json
from typing import Annotated, Generator

from dify_easy.model import (
    BasePlugin,
    Credential,
    CredentialType,
    FormType,
    MetaInfo,
    Param,
    ParamType,
    provider,
    tool,
)
from pydantic import BaseModel

from supabase import Client, create_client


class SupabaseCredentials(BaseModel):
    """
    Model for Supabase credentials.
    """

    url: Annotated[
        str,
        Credential(
            name="url",
            label="Supabase URL",
            placeholder="https://your-project.supabase.co",
            help="Enter your Supabase project URL.",
            url="https://supabase.com/dashboard/project/<project_id>/settings/api",
            type=CredentialType.text_input,
            required=True,
        ),
    ] = ""
    key: Annotated[
        str,
        Credential(
            name="key",
            label="Supabase Key",
            placeholder="Enter your Supabase key",
            help="Enter your Supabase API key.",
            url="https://supabase.com/dashboard/project/<project_id>/settings/api-keys",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""


class SupabasePlugin(BasePlugin):
    """
    Plugin for interacting with Supabase.
    """

    credentials: SupabaseCredentials = SupabaseCredentials()

    @provider
    def verify(self) -> None:
        """
        Verify the connection to Supabase.
        """
        client: Client = create_client(self.credentials.url, self.credentials.key)

        try:
            _ = response = client.storage.list_buckets()
        except Exception as e:
            raise ValueError(f"Failed to connect to Supabase: {e}")

    @tool(
        name="get_rows",
        label="Get Rows",
        description="Get rows from a specified table in Supabase.",
    )
    def get_rows(
        self,
        table: Annotated[
            str,
            Param(
                name="table",
                label="Table Name",
                description="The name of the table to query.",
                llm_description="Provide the name of the table you want to query in Supabase.",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        limit: Annotated[
            int,
            Param(
                name="limit",
                label="Limit",
                description="Maximum number of rows to return.",
                llm_description="Specify how many rows you want to retrieve. Default is 10.",
                type=ParamType.number,
                required=False,
                form=FormType.llm,
            ),
        ] = 10,
        filter: Annotated[
            str,
            Param(
                name="filter",
                label="Filter",
                description="Optional filter condition (e.g., 'status=active'). Multiple conditions can be separated by commas.",
                llm_description="Provide a filter condition if needed. (e.g., 'status=active,role=admin')",
                type=ParamType.string,
                required=False,
                form=FormType.llm,
            ),
        ] = "",
    ) -> Generator:
        """
        Get rows from a specified table.
        """
        client: Client = create_client(self.credentials.url, self.credentials.key)
        query = client.table(table).select("*")
        if filter:
            for cond in filter.split(","):
                if "=" in cond:
                    key, value = cond.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    query = query.eq(key, value)
        data = query.execute()
        yield data.data if hasattr(data, "data") else []

    @tool(
        name="create_a_row",
        label="Create a Row",
        description="Create a new row in a specified table in Supabase.",
    )
    def create_a_row(
        self,
        table: Annotated[
            str,
            Param(
                name="table",
                label="Table Name",
                description="The name of the table to insert into.",
                llm_description="Provide the name of the table where you want to insert a new row.",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        data: Annotated[
            str,
            Param(
                name="data",
                label="Row Data",
                description="Data for the new row as a JSON object.",
                llm_description="Provide the data for the new row in JSON format.",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ):
        """
        Create a new row in a specified table.
        """
        client: Client = create_client(self.credentials.url, self.credentials.key)
        res = client.table(table).insert(json.loads(data)).execute()
        yield res.data if hasattr(res, "data") else []

    # Update a row in a specified table
    @tool(
        name="update_rows",
        label="Update Row(s)",
        description="Update existing row(s) in a specified table in Supabase.",
    )
    def update_row(
        self,
        table: Annotated[
            str,
            Param(
                name="table",
                label="Table Name",
                description="The name of the table to update.",
                llm_description="Provide the name of the table where you want to update rows.",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        data: Annotated[
            str,
            Param(
                name="data",
                label="Row Data",
                description="Data for the row(s) to update as a JSON object.",
                llm_description="Provide the data for the row(s) to update in JSON format.",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        filter: Annotated[
            str,
            Param(
                name="filter",
                label="Filter",
                description="Optional filter condition (e.g., 'status=active'). Multiple conditions can be separated by commas.",
                llm_description="Provide a filter condition if needed. (e.g., 'status=active,role=admin')",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator:
        """
        Update existing row(s) in a specified table.
        """
        client: Client = create_client(self.credentials.url, self.credentials.key)
        query = client.table(table).update(json.loads(data))
        if filter:
            for cond in filter.split(","):
                if "=" in cond:
                    key, value = cond.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    query = query.eq(key, value)
        res = query.execute()
        yield res.data if hasattr(res, "data") else []

    # Delete a row in a specified table
    @tool(
        name="delete_rows",
        label="Delete Row(s)",
        description="Delete existing row(s) in a specified table in Supabase.",
    )
    def delete_row(
        self,
        table: Annotated[
            str,
            Param(
                name="table",
                label="Table Name",
                description="The name of the table to delete from.",
                llm_description="Provide the name of the table where you want to delete rows.",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        filter: Annotated[
            str,
            Param(
                name="filter",
                label="Filter",
                description="Optional filter condition (e.g., 'status=active'). Multiple conditions can be separated by commas.",
                llm_description="Provide a filter condition if needed. (e.g., 'status=active,role=admin')",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ):
        """
        Delete existing row(s) in a specified table.
        """
        client: Client = create_client(self.credentials.url, self.credentials.key)
        query = client.table(table).delete()
        if filter:
            for cond in filter.split(","):
                if "=" in cond:
                    key, value = cond.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    query = query.eq(key, value)

        res = query.execute()
        yield res.data if hasattr(res, "data") else []


plugin = SupabasePlugin(
    meta=MetaInfo(
        name="supabase",
        description="Plugin for interacting with Supabase databases.",
        version="0.1.0",
        author="langgenuis",
        label="Supabase",
        icon="icon.svg",
    )
)
