from typing import Generator, Union
from tools import trello_http as requests
from tools.trello_client import TrelloAuthError, credentials_of
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class FetchAllBoardsTool(Tool):
    """
    Tool for fetching all boards from Trello.
    """

    def _invoke(
        self, tool_parameters: dict[str, Union[str, int, bool]]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the fetch all boards tool.

        Args:
            user_id (str): The ID of the user invoking the tool.
            tool_parameters (dict[str, Union[str, int, bool]]): The parameters for the tool invocation.

        Returns:
            Union[ToolInvokeMessage, List[ToolInvokeMessage]]: The result of the tool invocation.
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
        if not (api_key and token):
            yield self.create_text_message(
                "Missing Trello API key or token in credentials."
            )
            return
        board_filter = tool_parameters.get("boards", "open")
        url = f"https://api.trello.com/1/members/me/boards?filter={board_filter}&key={api_key}&token={token}"
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Failed to fetch boards: {requests.reason(e)}")
            return
        boards = response.json()
        if not boards:
            yield self.create_text_message("No boards found in Trello.")
            return
        boards_info = ", ".join(
            [f"{board['name']} (ID: {board['id']})" for board in boards]
        )
        yield self.create_text_message(text=f"Boards: {boards_info}")
