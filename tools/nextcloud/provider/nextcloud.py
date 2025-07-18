from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class NextcloudProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Import webdavclient3 package (imported as webdav3.client)
            from webdav3.client import Client
            
            # Get credentials
            webdav_hostname = credentials.get("webdav_hostname")
            username = credentials.get("username")
            app_password = credentials.get("app_password")
            
            # Validate required credentials
            if not webdav_hostname:
                raise ToolProviderCredentialValidationError("NextCloud server URL is required.")
            if not username:
                raise ToolProviderCredentialValidationError("Username is required.")
            if not app_password:
                raise ToolProviderCredentialValidationError("App password is required.")
            
            # Ensure hostname ends with /remote.php/webdav
            if not webdav_hostname.endswith('/'):
                webdav_hostname += '/'
            if not webdav_hostname.endswith('remote.php/webdav/'):
                webdav_hostname += 'remote.php/webdav/'
            
            # Create WebDAV client options
            webdav_options = {
                'webdav_hostname': webdav_hostname,
                'webdav_login': username,
                'webdav_password': app_password
            }
            
            # Test connection by creating client and listing root directory
            client = Client(webdav_options)
            
            # Test basic connectivity by checking if we can list files
            try:
                client.list()
            except Exception as e:
                error_msg = str(e).lower()
                if 'unauthorized' in error_msg or '401' in error_msg:
                    raise ToolProviderCredentialValidationError("Invalid username or app password.")
                elif 'not found' in error_msg or '404' in error_msg:
                    raise ToolProviderCredentialValidationError("Invalid NextCloud server URL or WebDAV endpoint not found.")
                else:
                    raise ToolProviderCredentialValidationError(f"Failed to connect to NextCloud: {str(e)}")
                    
        except ImportError:
            raise ToolProviderCredentialValidationError("webdavclient3 library is required but not installed.")
        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Unexpected error during validation: {str(e)}")
