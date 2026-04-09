from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from neo4j_utils import Neo4jUtils


class Neo4jProvider(ToolProvider):

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check if required credentials are provided
            uri = credentials.get("uri")
            username = credentials.get("username")
            password = credentials.get("password")

            if not uri:
                raise ToolProviderCredentialValidationError("Neo4j URI is required.")

            if not username:
                raise ToolProviderCredentialValidationError("Neo4j username is required.")

            if not password:
                raise ToolProviderCredentialValidationError("Neo4j password is required.")

            # Try to connect to Neo4j
            try:
                Neo4jUtils.verify_connectivity(uri, username, password)
            except Exception as e:
                error_message = str(e)
                if "authentication" in error_message.lower() or "unauthorized" in error_message.lower():
                    raise ToolProviderCredentialValidationError(
                        f"Authentication failed. Please check your username and password: {error_message}"
                    )
                elif "connection" in error_message.lower() or "refused" in error_message.lower():
                    raise ToolProviderCredentialValidationError(
                        f"Failed to connect to Neo4j at {uri}. Please check the URI and ensure the database is running: {error_message}"
                    )
                else:
                    raise ToolProviderCredentialValidationError(
                        f"Failed to connect to Neo4j: {error_message}"
                    )

        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
