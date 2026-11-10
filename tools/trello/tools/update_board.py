from typing import Generator, Union
from tools import trello_http as requests
from tools.trello_client import TrelloAuthError, credentials_of
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class UpdateBoardByIdTool(Tool):
    """
    Tool for updating a Trello board by its ID with various parameters.
    """

    def _invoke(
        self, tool_parameters: dict[str, Union[str, int, bool, None]]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the tool to update a Trello board by its ID.

        Args:
            user_id (str): The ID of the user invoking the tool.
            tool_parameters (dict[str, Union[str, int, bool, None]]): The parameters for the tool invocation,
             including board ID and updates.

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
        board_id = tool_parameters.pop("boardId", None)
        if not (api_key and token and board_id):
            yield self.create_text_message(
                "Missing required parameters: API key, token, or board ID."
            )
            return
        url = f"https://api.trello.com/1/boards/{board_id}"
        params = {k: v for (k, v) in tool_parameters.items() if v is not None}
        params["key"] = api_key
        params["token"] = token
        try:
            response = requests.put(url, params=params)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to update board: {requests.reason(e)}")
            return
        updated_board = response.json()
        yield self.create_text_message(
            text=f"Board '{updated_board['name']}' updated successfully."
        )
