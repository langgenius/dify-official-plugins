import html
import json
import time
import urllib.parse
from collections.abc import Mapping

from werkzeug import Request, Response

from dify_plugin import Endpoint
from tools.user_auth import code_key, is_valid_state, signin_key

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;color:#1f2937}}
h1{{font-size:1.4rem}}p{{line-height:1.6}}
.note{{border-left:3px solid #d97706;padding-left:.75rem;color:#4b5563}}</style></head>
<body><h1>{title}</h1><p>{message}</p>{extra}</body></html>"""

# Someone could send a colleague their own sign-in link; the colleague's account would then
# be connected to the sender's chat. Say so, and let them withdraw it before it is redeemed.
_NOT_YOU = (
    '<p class="note">Only continue if you started this sign-in yourself, from your own chat. '
    'If someone else sent you this link, <a href="{cancel}">cancel this sign-in</a> now and tell your administrator.</p>'
)


def _page(title: str, message: str, status: int = 200, extra: str = "") -> Response:
    body = _PAGE.format(title=html.escape(title), message=html.escape(message), extra=extra)
    return Response(body, status=status, content_type="text/html; charset=utf-8")


class SignInCallbackEndpoint(Endpoint):
    """
    Redirect URI for per-user sign-in. Stores the authorization code under the state
    the tool issued; the tool redeems it (with the client secret,
    which this endpoint never sees) the next time the user asks for something.
    """

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        state = r.args.get("state", "")
        if not is_valid_state(state) or not self.session.storage.exist(signin_key(state)):
            return _page("Sign-in link not recognized", "This sign-in link is invalid or was already used. "
                         "Go back to the chat and ask again to get a new link.", 400)

        issued = json.loads(self.session.storage.get(signin_key(state)))
        if issued.get("expires_at", 0) < time.time():
            return _page("Sign-in link expired", "Go back to the chat and ask again to get a new link.", 400)

        if r.args.get("cancel"):
            self.session.storage.set(
                code_key(state), json.dumps({"error": "the person who opened the link cancelled the sign-in"}).encode()
            )
            return _page("Sign-in cancelled", "Your Atlassian account was not connected. You can close this tab.")

        error = r.args.get("error")
        if error:
            reason = r.args.get("error_description") or error
            self.session.storage.set(code_key(state), json.dumps({"error": reason[:500]}).encode())
            return _page("Sign-in failed", f"Atlassian reported: {reason}. Go back to the chat to try again.", 400)

        code = r.args.get("code")
        if not code:
            return _page("Sign-in failed", "Atlassian did not return an authorization code.", 400)

        self.session.storage.set(code_key(state), json.dumps({"code": code}).encode())
        cancel = "?" + urllib.parse.urlencode({"state": state, "cancel": "1"})
        return _page(
            "Signed in",
            "You can close this tab, go back to the chat and say you are done.",
            extra=_NOT_YOU.format(cancel=html.escape(cancel)),
        )
