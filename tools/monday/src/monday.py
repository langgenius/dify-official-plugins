import json
from dataclasses import asdict
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
from monday_sdk import MondayClient
from pydantic import BaseModel


class MondayCredential(BaseModel):
    token: Annotated[
        str,
        Credential(
            name="token",
            label="Monday API Token",
            placeholder="Enter your Monday API token",
            help="Your Monday API token can be found in https://<your-org>.monday.com/apps/manage/tokens",
            url="https://<your-org>.monday.com/apps/manage/tokens",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""


class MondayPlugin(BasePlugin):

    credentials: MondayCredential = MondayCredential()

    @provider
    def verify(self) -> None:
        client = MondayClient(token=self.credentials.token)
        try:
            _ = client.boards.fetch_boards(limit=1).data
        except Exception as e:
            raise ValueError(f"Failed to verify Monday API credentials: {e}")

        return None

    @tool(
        name="fetch_boards",
        label="Fetch Boards",
        description="Fetch boards from Monday.com",
    )
    def fetch_boards(
        self,
        limit: Annotated[
            int,
            Param(
                name="limit",
                label="Limit",
                description="The maximum number of boards to fetch, defaults to 20",
                type=ParamType.number,
                required=False,
                form=FormType.llm,
            ),
        ] = 20,
        page: Annotated[
            int,
            Param(
                name="page",
                label="Page",
                description="The page number to fetch, defaults to 1",
                type=ParamType.number,
                required=False,
                form=FormType.llm,
            ),
        ] = 1,
    ) -> Generator[list[dict], None, None]:
        client = MondayClient(token=self.credentials.token)
        response = client.boards.fetch_boards(limit=limit, page=page).data
        yield [asdict(board) for board in response.boards]

    @tool(
        name="fetch_board_by_id",
        label="Fetch Board by ID",
        description="Fetch a specific board from Monday.com by its ID.",
    )
    def fetch_board_by_id(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board to fetch",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator[dict, None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            board = client.boards.fetch_boards(ids=[int(board_id)]).data.boards[0]
            yield asdict(board)
        except Exception as e:
            raise ValueError(f"Failed to fetch board by ID: {e}")

    @tool(
        name="fetch_all_items_by_board_id",
        label="Fetch All Items by Board ID",
        description="Fetch all items from a specific board by its ID.",
    )
    def fetch_all_items_by_board_id(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board to fetch items from",
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
                description="The maximum number of items to fetch, defaults to 20",
                type=ParamType.number,
                required=False,
                form=FormType.llm,
            ),
        ] = 20,
    ) -> Generator[list[dict], None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            items = client.boards.fetch_all_items_by_board_id(
                board_id=int(board_id), limit=limit
            )
            yield [asdict(item) for item in items]
        except Exception as e:
            raise ValueError(f"Failed to fetch items by board ID: {e}")

    @tool(
        name="fetch_columns_by_board_id",
        label="Fetch Columns by Board ID",
        description="Fetch all columns from a specific board by its ID.",
    )
    def fetch_columns_by_board_id(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board to fetch columns from",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator[list[dict], None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            columns = (
                client.boards.fetch_columns_by_board_id(board_id=int(board_id))
                .data.boards[0]
                .columns
            )
            yield [asdict(column) for column in columns]
        except Exception as e:
            raise ValueError(f"Failed to fetch columns by board ID: {e}")

    @tool(
        name="fetch_groups_by_board_id",
        label="Fetch Groups by Board ID",
        description="Fetch all groups from a specific board by its ID.",
    )
    def fetch_groups_by_board_id(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board to fetch groups from",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator[list[dict], None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            groups = (
                client.boards.fetch_boards_by_id(board_id=int(board_id))
                .data.boards[0]
                .groups
            )
            yield [asdict(group) for group in groups]
        except Exception as e:
            raise ValueError(f"Failed to fetch groups by board ID: {e}")

    @tool(
        name="create_item",
        label="Create Item",
        description="Create an item in a specific board and group.",
    )
    def create_item(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board to create the item in",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        group_id: Annotated[
            str,
            Param(
                name="group_id",
                label="Group ID",
                description="The ID or title of the group to create the item in",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        item_name: Annotated[
            str,
            Param(
                name="item_name",
                label="Item Name",
                description="The name of the item to create",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        column_values: Annotated[
            str,
            Param(
                name="column_values",
                label="Column Values",
                description="A dictionary of column values for the item, for example: {'name': 'Test Item'}",
                type=ParamType.string,
                required=False,
                form=FormType.llm,
            ),
        ] = {},
    ) -> Generator[dict, None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            item = client.items.create_item(
                board_id=int(board_id),
                group_id=group_id,
                item_name=item_name,
                column_values=json.loads(column_values) if column_values else {},
            ).data.create_item
            yield asdict(item)
        except Exception as e:
            raise ValueError(f"Failed to create item: {e}")

    @tool(
        name="create_item_update",
        label="Create Item Update",
        description="Create an update for a specific item.",
    )
    def create_item_update(
        self,
        item_id: Annotated[
            str,
            Param(
                name="item_id",
                label="Item ID",
                description="The ID of the item to update",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        update_value: Annotated[
            str,
            Param(
                name="update_value",
                label="Update Value",
                description="The content of the update",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator[dict, None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            res = client.updates.create_update(
                item_id=int(item_id), update_value=update_value
            ).data
            yield asdict(res)
        except Exception as e:
            raise ValueError(f"Failed to create item update: {e}")

    @tool(
        name="change_item_status",
        label="Change Item Status",
        description="Change the status column value of an item.",
    )
    def change_item_status(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board containing the item",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        item_id: Annotated[
            str,
            Param(
                name="item_id",
                label="Item ID",
                description="The ID of the item to update",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        column_id: Annotated[
            str,
            Param(
                name="column_id",
                label="Column ID",
                description="The ID of the status column to update",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        status_label: Annotated[
            str,
            Param(
                name="status_label",
                label="Status Label",
                description="The new status label value",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator[dict, None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            res = client.items.change_status_column_value(
                board_id=int(board_id),
                item_id=int(item_id),
                column_id=column_id,
                value=status_label,
            )
            yield asdict(res)
        except Exception as e:
            raise ValueError(f"Failed to change item status: {e}")

    @tool(
        name="change_item_column_value",
        label="Change Item Column Value",
        description="Change a simple column value of an item.",
    )
    def change_item_column_value(
        self,
        board_id: Annotated[
            str,
            Param(
                name="board_id",
                label="Board ID",
                description="The ID of the board containing the item",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        item_id: Annotated[
            str,
            Param(
                name="item_id",
                label="Item ID",
                description="The ID of the item to update",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        column_id: Annotated[
            str,
            Param(
                name="column_id",
                label="Column ID",
                description="The ID of the column to update",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
        value: Annotated[
            str,
            Param(
                name="value",
                label="Value",
                description="The new value for the column",
                type=ParamType.string,
                required=True,
                form=FormType.llm,
            ),
        ],
    ) -> Generator[dict, None, None]:
        client = MondayClient(token=self.credentials.token)
        try:
            res = client.items.change_simple_column_value(
                board_id=int(board_id),
                item_id=int(item_id),
                column_id=column_id,
                value=value,
            )
            yield asdict(res)
        except Exception as e:
            raise ValueError(f"Failed to change item column value: {e}")


plugin = MondayPlugin(
    meta=MetaInfo(
        name="monday",
        author="langgenius",
        label="Monday.com",
        description="A plugin to interact with Monday.com boards, items, and updates.",
        version="0.0.1",
        icon="icon.svg",
    )
)
