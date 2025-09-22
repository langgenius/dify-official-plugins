from typing import Any, Mapping
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import ClientSecretCredential
import re
import requests
import urllib.parse
from flask import Request

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
from dify_plugin.errors.tool import DatasourceOAuthError


class AzureBlobDatasourceProvider(DatasourceProvider):

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        """Validate credential validity"""
        auth_method = credentials.get("auth_method", "account_key")
        account_name = credentials.get("account_name")
        endpoint_suffix = credentials.get("endpoint_suffix", "core.windows.net")
        
        if not account_name:
            raise ValueError("Storage account name is required")
        
        # Validate account name format
        if not self._is_valid_account_name(account_name):
            raise ValueError("Invalid storage account name. Must be 3-24 characters, lowercase letters and numbers only")
        
        # Validate corresponding credentials based on authentication method
        if auth_method == "account_key":
            account_key = credentials.get("account_key")
            if not account_key or account_key.strip() == "":
                raise ValueError("Account key is required when using account key authentication")
            self._validate_account_key_access(account_name, account_key, endpoint_suffix)
            
        elif auth_method == "sas_token":
            sas_token = credentials.get("sas_token")
            if not sas_token or sas_token.strip() == "":
                raise ValueError("SAS token is required when using SAS token authentication")
            self._validate_sas_token_access(account_name, sas_token, endpoint_suffix)
            
        elif auth_method == "connection_string":
            connection_string = credentials.get("connection_string")
            if not connection_string or connection_string.strip() == "":
                raise ValueError("Connection string is required when using connection string authentication")
            self._validate_connection_string_access(connection_string)
            
        elif auth_method == "oauth":
            access_token = credentials.get("access_token")
            if not access_token or access_token.strip() == "":
                raise ValueError("Access token is required. Please complete OAuth authorization first")
            self._validate_oauth_access(credentials)
            
        else:
            raise ValueError(f"Unsupported authentication method: {auth_method}")

    def _is_valid_account_name(self, account_name: str) -> bool:
        """Validate Azure storage account name format"""
        if not account_name or len(account_name) < 3 or len(account_name) > 24:
            return False
        return bool(re.match(r'^[a-z0-9]+$', account_name))

    def _validate_account_key_access(self, account_name: str, account_key: str, endpoint_suffix: str) -> None:
        """Validate account key access"""
        try:
            account_url = f"https://{account_name}.blob.{endpoint_suffix}"
            blob_service_client = BlobServiceClient(
                account_url=account_url,
                credential=account_key
            )
            
            # Try to list containers to verify access permissions
            containers_iter = blob_service_client.list_containers()
            # Only get first container to verify access permissions
            containers = []
            for container in containers_iter:
                containers.append(container)
                break  # Only get one for verification
            # Successfully listing containers or getting empty list indicates successful authentication
            
        except ClientAuthenticationError as e:
            raise ValueError(f"Invalid account key or insufficient permissions: {str(e)}")
        except AzureError as e:
            if "AuthenticationFailed" in str(e):
                raise ValueError(f"Authentication failed: {str(e)}")
            elif "AccountIsDisabled" in str(e):
                raise ValueError("Storage account is disabled")
            elif "InvalidResourceName" in str(e):
                raise ValueError("Invalid storage account name")
            else:
                raise ValueError(f"Azure Storage error: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to validate Azure Blob Storage credentials: {str(e)}")

    def _validate_sas_token_access(self, account_name: str, sas_token: str, endpoint_suffix: str) -> None:
        """Validate SAS token access"""
        try:
            # Ensure SAS token starts with ?
            if not sas_token.startswith('?'):
                sas_token = '?' + sas_token
            
            account_url = f"https://{account_name}.blob.{endpoint_suffix}"
            blob_service_client = BlobServiceClient(
                account_url=account_url + sas_token
            )
            
            # Try to list containers to verify SAS permissions
            containers_iter = blob_service_client.list_containers()
            # Only get first container to verify SAS permissions
            containers = []
            for container in containers_iter:
                containers.append(container)
                break  # Only get one for verification
            
        except ClientAuthenticationError as e:
            raise ValueError(f"Invalid SAS token or insufficient permissions: {str(e)}")
        except AzureError as e:
            if "AuthenticationFailed" in str(e):
                raise ValueError("SAS token authentication failed. Please check token validity and permissions")
            elif "AuthorizationPermissionMismatch" in str(e):
                raise ValueError("SAS token does not have required permissions (read and list)")
            elif "InvalidQueryParameterValue" in str(e):
                raise ValueError("Invalid SAS token format")
            else:
                raise ValueError(f"SAS token validation error: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to validate SAS token: {str(e)}")

    def _validate_connection_string_access(self, connection_string: str) -> None:
        """Validate connection string access"""
        try:
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            
            # Try to list containers to verify connection
            containers_iter = blob_service_client.list_containers()
            # Only get first container to verify connection
            containers = []
            for container in containers_iter:
                containers.append(container)
                break  # Only get one for verification
            
        except ClientAuthenticationError as e:
            raise ValueError(f"Invalid connection string or insufficient permissions: {str(e)}")
        except ValueError as e:
            if "connection string" in str(e).lower():
                raise ValueError("Invalid connection string format")
            raise e
        except AzureError as e:
            if "AuthenticationFailed" in str(e):
                raise ValueError("Connection string authentication failed")
            else:
                raise ValueError(f"Connection string validation error: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to validate connection string: {str(e)}")

    def _get_account_url(self, account_name: str, endpoint_suffix: str) -> str:
        """Build storage account URL"""
        return f"https://{account_name}.blob.{endpoint_suffix}"

    def _create_blob_service_client(self, credentials: Mapping[str, Any]) -> BlobServiceClient:
        """Create Blob service client"""
        auth_method = credentials.get("auth_method", "account_key")
        account_name = credentials.get("account_name")
        endpoint_suffix = credentials.get("endpoint_suffix", "core.windows.net")
        
        if auth_method == "account_key":
            account_key = credentials.get("account_key")
            account_url = self._get_account_url(account_name, endpoint_suffix)
            return BlobServiceClient(account_url=account_url, credential=account_key)
            
        elif auth_method == "sas_token":
            sas_token = credentials.get("sas_token")
            if not sas_token.startswith('?'):
                sas_token = '?' + sas_token
            account_url = self._get_account_url(account_name, endpoint_suffix)
            return BlobServiceClient(account_url=account_url + sas_token)
            
        elif auth_method == "connection_string":
            connection_string = credentials.get("connection_string")
            return BlobServiceClient.from_connection_string(connection_string)
            
        elif auth_method == "oauth":
            access_token = credentials.get("access_token")
            account_url = self._get_account_url(account_name, endpoint_suffix)
            
            # Create simple token credential
            from azure.core.credentials import AccessToken
            from datetime import datetime, timezone
            
            class SimpleTokenCredential:
                def __init__(self, token, expires_in=3600):
                    self.token = token
                    self.expires_at = int(datetime.now(timezone.utc).timestamp()) + expires_in
                
                def get_token(self, *scopes, **kwargs):
                    current_time = int(datetime.now(timezone.utc).timestamp())
                    if current_time >= self.expires_at - 300:  # Refresh 5 minutes early
                        raise ClientAuthenticationError("Access token has expired, refresh required")
                    return AccessToken(self.token, self.expires_at)
            
            credential = SimpleTokenCredential(access_token)
            return BlobServiceClient(account_url=account_url, credential=credential)
            
        else:
            raise ValueError(f"Unsupported authentication method: {auth_method}")

    def _get_storage_info(self, credentials: Mapping[str, Any]) -> dict:
        """Get storage account information (for validation and metadata)"""
        try:
            blob_service_client = self._create_blob_service_client(credentials)
            account_info = blob_service_client.get_account_information()
            
            return {
                "account_kind": account_info.get("account_kind", "Unknown"),
                "sku_name": account_info.get("sku_name", "Unknown"),
                "is_hns_enabled": account_info.get("is_hns_enabled", False)
            }
        except Exception:
            # If unable to get account info, return basic info
            return {
            "account_kind": "StorageV2",
            "sku_name": "Standard_LRS", 
            "is_hns_enabled": False
        }

    def _validate_oauth_access(self, credentials: Mapping[str, Any]) -> None:
        """Validate OAuth access"""
        try:
            account_name = credentials.get("account_name")
            endpoint_suffix = credentials.get("endpoint_suffix", "core.windows.net")
            access_token = credentials.get("access_token")
            
            if not account_name:
                raise ValueError("Storage account name is required for OAuth authentication")
            
            # Create BlobServiceClient using access token
            account_url = f"https://{account_name}.blob.{endpoint_suffix}"
            
            # Use TokenCredential approach
            from azure.core.credentials import AccessToken
            from azure.identity import AccessTokenCredential
            from datetime import datetime, timezone
            
            # Create a simple token credential
            class SimpleTokenCredential:
                def __init__(self, token, expires_in=3600):
                    self.token = token
                    self.expires_at = int(datetime.now(timezone.utc).timestamp()) + expires_in
                
                def get_token(self, *scopes, **kwargs):
                    current_time = int(datetime.now(timezone.utc).timestamp())
                    if current_time >= self.expires_at - 300:  # Refresh 5 minutes early
                        raise ClientAuthenticationError("Access token has expired, refresh required")
                    return AccessToken(self.token, self.expires_at)
            
            credential = SimpleTokenCredential(access_token)
            blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
            
            # Try to list containers to verify permissions
            containers_iter = blob_service_client.list_containers()
            # Only get first container to verify permissions
            containers = []
            for container in containers_iter:
                containers.append(container)
                break  # Only get one for verification
                
        except ClientAuthenticationError as e:
            raise ValueError(f"Invalid OAuth token or insufficient permissions: {str(e)}")
        except AzureError as e:
            if "AuthenticationFailed" in str(e):
                raise ValueError("OAuth authentication failed. Please check access token validity")
            else:
                raise ValueError(f"OAuth validation error: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error validating OAuth access: {str(e)}")

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """Get OAuth authorization URL"""
        client_id = system_credentials.get("client_id")
        tenant_id = system_credentials.get("tenant_id")
        cloud_environment = system_credentials.get("cloud_environment", "global")
        
        if not client_id or not tenant_id:
            raise ValueError("Incomplete OAuth configuration: missing client_id or tenant_id")
        
        # Get login endpoint and scope based on cloud environment
        login_endpoint, storage_scope = self._get_cloud_endpoints(cloud_environment)
        
        auth_url = f"https://{login_endpoint}/{tenant_id}/oauth2/v2.0/authorize"
        
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": storage_scope,
            "response_mode": "query",
            "prompt": "consent"  # Ensure user consents to permissions
        }
        
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """Get OAuth credentials"""
        code = request.args.get("code")
        if not code:
            raise ValueError("Authorization code not found")
        
        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")
        tenant_id = system_credentials.get("tenant_id")
        cloud_environment = system_credentials.get("cloud_environment", "global")
        
        if not all([client_id, client_secret, tenant_id]):
            raise ValueError("Incomplete OAuth configuration")
        
        # Get login endpoint based on cloud environment
        login_endpoint, storage_scope = self._get_cloud_endpoints(cloud_environment)
        
        # Exchange authorization code for access token
        token_url = f"https://{login_endpoint}/{tenant_id}/oauth2/v2.0/token"
        
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": storage_scope
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        try:
            response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
            
            if response.status_code != 200:
                error_detail = response.text
                raise ValueError(f"Failed to obtain access token: {error_detail}")
            
            token_json = response.json()
            access_token = token_json.get("access_token")
            refresh_token = token_json.get("refresh_token")
            
            if not access_token:
                raise ValueError("Failed to obtain access token")
            
            # Note: client_secret is not returned here
            return DatasourceOAuthCredentials(
                credentials={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "tenant_id": tenant_id
                }
            )
            
        except requests.RequestException as e:
            raise ValueError(f"Error requesting access token: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error in OAuth authentication process: {str(e)}")

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """Refresh access token"""
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        tenant_id = credentials.get("tenant_id")
        
        # Note: client_secret needs to be obtained from system configuration, not from credentials
        # In actual implementation, client_secret may need to be obtained through other means
        if not refresh_token or not client_id or not tenant_id:
            raise ValueError("Incomplete credentials required for token refresh")
        
        # Need to get client_secret here, but cannot get it from user credentials
        raise ValueError("Access token has expired, please re-authorize OAuth")


    def _oauth_refresh_credentials(self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]) -> DatasourceOAuthCredentials:
        """OAuth refresh credentials method - interface required by Dify framework"""
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id") or system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")  # Get from system configuration
        tenant_id = credentials.get("tenant_id") or system_credentials.get("tenant_id")
        cloud_environment = system_credentials.get("cloud_environment", "global")
        
        if not refresh_token:
            raise DatasourceOAuthError("No refresh token available, please re-authorize OAuth")
        
        if not all([client_id, client_secret, tenant_id]):
            raise DatasourceOAuthError("Incomplete OAuth refresh configuration")
        
        # Get login endpoint based on cloud environment
        login_endpoint, storage_scope = self._get_cloud_endpoints(cloud_environment)
        
        # Refresh access token
        token_url = f"https://{login_endpoint}/{tenant_id}/oauth2/v2.0/token"
        
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": storage_scope
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        try:
            response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
            
            if response.status_code != 200:
                error_detail = response.text
                raise DatasourceOAuthError(f"Failed to refresh access token: {error_detail}")
            
            token_json = response.json()
            new_access_token = token_json.get("access_token")
            new_refresh_token = token_json.get("refresh_token", refresh_token)  # Use new or keep existing
            
            if not new_access_token:
                raise DatasourceOAuthError("Failed to obtain new access token")
            

            return DatasourceOAuthCredentials(
                credentials={
                    "access_token": new_access_token,
                    "refresh_token": new_refresh_token,
                    "client_id": client_id,
                    "tenant_id": tenant_id
                }
            )
            
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Token refresh request failed: {str(e)}")
        except Exception as e:
            raise DatasourceOAuthError(f"Error in OAuth refresh process: {str(e)}")

    def _get_cloud_endpoints(self, cloud_environment: str) -> tuple[str, str]:
        """Get endpoints and scope for different cloud environments"""
        if cloud_environment == "china":
            return "login.chinacloudapi.cn", "https://storage.azure.cn/user_impersonation"
        elif cloud_environment == "government":
            return "login.microsoftonline.us", "https://storage.azure.us/user_impersonation"
        elif cloud_environment == "germany":
            return "login.microsoftonline.de", "https://storage.azure.de/user_impersonation"
        else:  # global (default)
            return "login.microsoftonline.com", "https://storage.azure.com/user_impersonation"
