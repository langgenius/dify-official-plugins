from dify_plugin import ToolProvider


class DifyExtractorProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, object]) -> None:
        """The extractor has no provider credentials to validate."""
        return None
