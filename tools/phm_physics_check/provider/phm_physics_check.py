from dify_plugin import ToolProvider


class PhmPhysicsCheckProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        # No credentials needed: the checker is fully offline.
        pass
