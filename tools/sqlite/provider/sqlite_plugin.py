from typing import Any
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
import os
import sqlite3

class SQLiteConnectionManager:
    def __init__(self, database_path: str, timeout: int = 30):
        self.database_path = database_path
        self.timeout = timeout

    def validate(self):
        """Check if the file exists and is a valid SQLite database."""
        if not self.database_path:
            raise ValueError("Database file path is required.")
        if not os.path.isfile(self.database_path):
            raise FileNotFoundError(f"Database file does not exist: {self.database_path}")
        try:
            with sqlite3.connect(self.database_path, timeout=self.timeout) as conn:
                conn.execute("SELECT 1")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to database: {e}")

    def get_connection(self):
        """Get a connection to the SQLite database."""
        self.validate()
        return sqlite3.connect(self.database_path, timeout=self.timeout)

class SqlitePluginProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            database_path = credentials.get("database_path")
            if not database_path:
                raise ToolProviderCredentialValidationError("Database file path is required.")
            manager = SQLiteConnectionManager(database_path=database_path)
            manager.validate()
        except (ValueError, FileNotFoundError, ConnectionError) as e:
            raise ToolProviderCredentialValidationError(str(e))
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Unexpected error: {e}")
