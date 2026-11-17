from typing import Generator, Union
from tools import trello_http as requests
from tools.trello_client import TrelloAuthError, credentials_of
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class CreateBoardTool(Tool):
    """
    Tool for creating a new Trello board.
    """

    def _invoke(
        self, tool_parameters: dict[str, Union[str, int, bool]]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the tool to create a new Trello board.

        Args:
            user_id (str): The ID of the user invoking the tool.
            tool_parameters (dict[str, Union[str, int, bool]]): The parameters for the tool invocation.

        Returns:
            ToolInvokeMessage: The result of the tool invocation.
        """
        try:
            api_key, token = credentials_of(self)
        except TrelloAuthError as e:
            # For per-user sign-in this is the link the user has to open.
            yield self.create_text_message(str(e))
            return
        if getattr(self, "_signed_in_as", None):
            yield self.create_text_message(
                f"(Signed in to Trello as {self._signed_in_as}. If this is not the user's account, "
                "they can ask to sign out and sign in again.)"
            )
        board_name = tool_parameters.get("name")
        if not (api_key and token and board_name):
            yield self.create_text_message(
                "Missing required parameters: API key, token, or board name."
            )
            return
        url = "https://api.trello.com/1/boards/"
        query_params = {"name": board_name, "key": api_key, "token": token}
        workspace = str(tool_parameters.get("idOrganization") or "").strip()
        try:
            if not workspace:
                # Boards must belong to a Workspace; without one Trello tries to create a Workspace and
                # fails ("Unable to auto-create an organization"). Use the account's first Workspace.
                orgs = requests.get(
                    "https://api.trello.com/1/members/me/organizations",
                    params={"fields": "id,displayName", "key": api_key, "token": token},
                )
                orgs.raise_for_status()
                workspace = next((o["id"] for o in orgs.json()), "")
            if workspace:
                query_params["idOrganization"] = workspace
            response = requests.post(url, params=query_params)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to create board: {requests.reason(e)}")
            return
        board = response.json()
        yield self.create_text_message(
            text=f"Board created successfully! Board name: {board['name']}, ID: {board['id']}"
        )
