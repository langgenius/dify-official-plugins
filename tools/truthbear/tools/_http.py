# DO NOT EDIT — generated from truth/ by scripts/gen.mjs
# truth-sha: 540d5ca39fd40903
# Edit truth/service.json or truth/tools.json instead, then run: node scripts/gen.mjs

"""Shared HTTP layer. Standard library only - this plugin has no third-party HTTP dependency."""
import json
import urllib.error
import urllib.parse
import urllib.request

from _config import BASE_URL

TIMEOUT_SECONDS = 30


def call(path: str, params: dict) -> tuple[int, dict]:
    """GET one endpoint. Returns (status, parsed_body).

    A non-2xx status is NOT an exception here: this service answers 402 with a payment
    challenge and 422 with an honest "not charged" explanation, and both of those are
    information the caller wants, not failures to hide.
    """
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    url = BASE_URL + path
    if clean:
        url += "?" + urllib.parse.urlencode(clean)
    req = urllib.request.Request(url, method="GET", headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as res:
            return res.status, _parse(res.read())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read())


def _parse(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        # Handing back what the server actually said beats inventing a shape it never sent.
        return {"_non_json_body": raw.decode("utf-8", "replace")[:2000]}
