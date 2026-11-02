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
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;color:#1f2937}}
h1{{font-size:1.4rem}}p{{line-height:1.6}}
.note{{border-left:3px solid #d97706;padding-left:.75rem;color:#4b5563}}</style></head>
<body><h1 id="title">{title}</h1><p id="message">{message}</p>{extra}</body></html>"""

# Someone could send a colleague their own sign-in link; the colleague's account would then
# be connected to the sender's chat. Say so, and let them withdraw it before it is used.
_NOT_YOU = (
    '<p class="note">Only continue if you started this sign-in yourself, from your own chat. '
    'If someone else sent you this link, <a href="{cancel}">cancel this sign-in</a> now and tell your administrator.</p>'
)

# Trello puts the token in the URL fragment, which never reaches the server. This script sends
# it to the same URL by POST, then removes it from the address bar and history.
_SCRIPT = """<script>
(function () {
  var params = new URLSearchParams(location.hash.slice(1));
  var token = params.get("token");
  history.replaceState(null, "", location.pathname + location.search);
  var title = document.getElementById("title"), message = document.getElementById("message");
  if (!token) {
    title.textContent = "Sign-in not completed";
    message.textContent = "Trello did not return a token (access was not allowed). Go back to the chat to try again.";
    return;
  }
  fetch(location.pathname + location.search, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token: token}),
    credentials: "omit", cache: "no-store"
  }).then(function (r) {
    if (!r.ok) { throw new Error(r.status); }
    title.textContent = "Signed in";
    message.textContent = "You can close this tab, go back to the chat and say you are done.";
    document.getElementById("not-you").style.display = "block";
  }).catch(function () {
    title.textContent = "Sign-in failed";
    message.textContent = "The sign-in link is invalid or has expired. Go back to the chat and ask again to get a new link.";
  });
})();
</script>"""


def _page(title: str, message: str, status: int = 200, extra: str = "") -> Response:
    body = _PAGE.format(title=html.escape(title), message=html.escape(message), extra=extra)
    return Response(body, status=status, content_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def pending_sign_in(storage, state: str) -> dict | None:
    """The sign-in issued for this state, if it exists and has not expired."""
    if not is_valid_state(state) or not storage.exist(signin_key(state)):
        return None
    issued = json.loads(storage.get(signin_key(state)))
    return issued if issued.get("expires_at", 0) >= time.time() else None


class SignInCallbackEndpoint(Endpoint):
    """
    Return URL of the Trello authorize page (GET). Serves a page whose script reads the token
    from the URL fragment and posts it to ``SignInTokenEndpoint``; also handles "cancel".
    """

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        state = r.args.get("state", "")
        if pending_sign_in(self.session.storage, state) is None:
            return _page("Sign-in link not recognized", "This sign-in link is invalid, expired or was already used. "
                         "Go back to the chat and ask again to get a new link.", 400)

        if r.args.get("cancel"):
            self.session.storage.set(
                code_key(state), json.dumps({"error": "the person who opened the link cancelled the sign-in"}).encode()
            )
            return _page("Sign-in cancelled", "Your Trello account was not connected. You can close this tab.")

        cancel = "?" + urllib.parse.urlencode({"state": state, "cancel": "1"})
        extra = (
            f'<div id="not-you" style="display:none">{_NOT_YOU.format(cancel=html.escape(cancel))}</div>' + _SCRIPT
        )
        return _page("Signing in…", "Finishing the Trello sign-in.", extra=extra)
