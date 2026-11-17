from typing import Generator, Union
from tools import trello_http as requests
from tools.trello_client import TrelloAuthError, credentials_of
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GetFilteredBoardCardsTool(Tool):
    """
    Tool for retrieving filtered cards on a Trello board by its ID and a specified filter.
    """

    def _invoke(
        self, tool_parameters: dict[str, Union[str, int, bool]]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the tool to retrieve filtered cards on a Trello board by its ID and filter.

        Args:
            user_id (str): The ID of the user invoking the tool.
            tool_parameters (dict[str, Union[str, int, bool]]): The parameters for the tool invocation,
             including the board ID and filter.

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
        filter = tool_parameters.get("filter")
        if not (api_key and token and board_id and filter):
            yield self.create_text_message(
                "Missing required parameters: API key, token, board ID, or filter."
            )
            return
        url = f"https://api.trello.com/1/boards/{board_id}/cards/{filter}?key={api_key}&token={token}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            filtered_cards = response.json()
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to retrieve filtered cards: {requests.reason(e)}")
            return
        card_details = "\n".join(
            [f"{card['name']} (ID: {card['id']})" for card in filtered_cards]
        )
        yield self.create_text_message(
            text=f"Filtered Cards for Board ID {board_id} with Filter '{filter}':\n{card_details}"
        )
