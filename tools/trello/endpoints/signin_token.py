import json
import re
from collections.abc import Mapping

from werkzeug import Request, Response

from dify_plugin import Endpoint
from endpoints.signin_callback import pending_sign_in
from tools.user_auth import code_key, seal

# Trello tokens: 64 hex characters, or the newer ATTA... form.
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


def _json(body: dict, status: int = 200) -> Response:
    return Response(json.dumps(body), status=status, content_type="application/json", headers={"Cache-Control": "no-store"})


class SignInTokenEndpoint(Endpoint):
    """
    Receives the token from the callback page (POST) and stores it sealed with the sign-in's
    public key. Only the tool holds the private key, so the stored value cannot be read here.
    """

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        state = r.args.get("state", "")
        issued = pending_sign_in(self.session.storage, state)
        if issued is None or not issued.get("public_key"):
            return _json({"ok": False, "error": "unknown or expired sign-in"}, 400)
        if self.session.storage.exist(code_key(state)):
            # Each link is used once; a second post cannot replace the first token.
            return _json({"ok": False, "error": "this sign-in was already completed"}, 409)
        try:
            token = str((json.loads(r.get_data(as_text=True) or "{}") or {}).get("token") or "")
        except ValueError:
            token = ""
        if not _TOKEN.match(token):
            return _json({"ok": False, "error": "no valid token"}, 400)
        self.session.storage.set(code_key(state), json.dumps({"sealed": seal(issued["public_key"], token)}).encode())
        return _json({"ok": True})
