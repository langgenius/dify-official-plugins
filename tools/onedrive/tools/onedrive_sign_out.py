from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphAuthError, is_per_user, user_sign_in
from tools.outputs import with_outputs


class SignOutTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Forget the calling user's Microsoft token (per-user sign-in only)."""
        if not is_per_user(self.runtime.credentials):
            yield self.create_text_message(
                "Sign-out only applies to the 'Each user signs in' credential mode; this credential is shared "
                "by the workspace and is managed in the tool's authorization settings."
            )
            return
        try:
            sign_in = user_sign_in(self.runtime.credentials, self)
            account = sign_in.account()
            signed_in = sign_in.sign_out()
        except GraphAuthError as e:
            yield self.create_text_message(str(e))
            return
        self._out.update(signed_out=signed_in, success=True)
        yield self.create_text_message(
            f"Signed out of Microsoft{f' ({account})' if account else ''}. "
            "The next request will ask the user to sign in again."
            if signed_in
            else "The user was not signed in."
        )
