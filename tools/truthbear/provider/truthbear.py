# DO NOT EDIT — generated from truth/ by scripts/gen.mjs
# truth-sha: 540d5ca39fd40903
# Edit truth/service.json or truth/tools.json instead, then run: node scripts/gen.mjs

from dify_plugin import ToolProvider


class TruthBearProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        """This plugin takes no credentials.

        The free tools need no key and no wallet. The paid tool never pays - it returns the
        service's live payment challenge as data, so there is nothing to validate here.
        """
        return None
