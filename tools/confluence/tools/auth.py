from typing import Any, Generator

from atlassian import ConfluenceV2
from atlassian.confluence import ConfluenceServer

from tools.confluence_client import ConfluenceAuthError, auth  # noqa: F401  (auth: kept for existing imports)


def connect(tool: Any) -> Generator[Any, None, ConfluenceV2 | ConfluenceServer | None]:
    """
    ``confluence = yield from connect(self)`` in a tool's _invoke: the client for the tool's credential,
    or None after yielding the reason (for per-user sign-in, the link the user has to open).
    """
    try:
        confluence = auth(tool.runtime.credentials, tool)
    except ConfluenceAuthError as e:
        yield tool.create_text_message(str(e))
        return None
    if getattr(tool, "_signed_in_as", None):
        yield tool.create_text_message(
            f"(Signed in to Atlassian as {tool._signed_in_as}. If this is not the user's account, "
            "they can ask to sign out and sign in again.)"
        )
    return confluence
