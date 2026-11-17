from typing import Generator, Union
from tools import trello_http as requests
from tools.trello_client import TrelloAuthError, credentials_of
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GetBoardCardsTool(Tool):
    """
    Tool for retrieving cards on a Trello board by its ID.
    """

    def _invoke(
        self, tool_parameters: dict[str, Union[str, int, bool]]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the tool to retrieve cards on a Trello board by its ID.

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
        url = f"https://api.trello.com/1/boards/{board_id}/cards?key={api_key}&token={token}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            cards = response.json()
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to retrieve board cards: {requests.reason(e)}")
            return
        cards_summary = "\n".join(
            [f"{card['name']} (ID: {card['id']})" for card in cards]
        )
        yield self.create_text_message(
            text=f"Cards for Board ID {board_id}:\n{cards_summary}"
        )
