from typing import Generator, Union
from tools import trello_http as requests
from tools.trello_client import TrelloAuthError, credentials_of
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GetBoardByIdTool(Tool):
    """
    Tool for retrieving detailed information about a Trello board by its ID.
    """

    def _invoke(
        self, tool_parameters: dict[str, Union[str, int, bool]]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the tool to retrieve a Trello board by its ID.

        Args:
            user_id (str): The ID of the user invoking the tool.
            tool_parameters (dict[str, Union[str, int, bool]]): The parameters for the tool invocation,
             including the board ID.

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
        board_id = tool_parameters.get("boardId")
        if not (api_key and token and board_id):
            yield self.create_text_message(
                "Missing required parameters: API key, token, or board ID."
            )
            return
        url = f"https://api.trello.com/1/boards/{board_id}?key={api_key}&token={token}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            board = response.json()
            board_details = self.format_board_details(board)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to retrieve board: {requests.reason(e)}")
            return
        yield self.create_text_message(text=board_details)

    def format_board_details(self, board: dict) -> str:
        """
        Format the board details into a human-readable string.

        Args:
            board (dict): The board information as a dictionary.

        Returns:
            str: Formatted board details.
        """
        details = f"Board Name: {board['name']}\nBoard ID: {board['id']}\nDescription: {board['desc'] or 'No description provided.'}\nStatus: {('Closed' if board['closed'] else 'Open')}\nOrganization ID: {board['idOrganization'] or 'Not part of an organization.'}\nURL: {board['url']}\nShort URL: {board['shortUrl']}\nPermission Level: {board['prefs']['permissionLevel']}\nBackground Color: {board['prefs']['backgroundColor']}"
        return details
