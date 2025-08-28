import base64
import logging
from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

logger = logging.getLogger(__name__)


class LinuxdoProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        验证LinuxDo Connect认证信息
        """
        try:
            client_id = credentials.get("client_id")
            client_secret = credentials.get("client_secret")
            api_key = credentials.get("api_key")
            
            if not client_id:
                raise ToolProviderCredentialValidationError("Client ID 不能为空")
            if not client_secret:
                raise ToolProviderCredentialValidationError("Client Secret 不能为空")
            if not api_key:
                raise ToolProviderCredentialValidationError("API Key 不能为空")
            
            # 创建Basic Authorization
            credential = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers = {
                "Authorization": f"Basic {credential}",
                "User-Agent": "Dify LinuxDo Plugin/1.0"
            }
            
            # 验证API Key
            response = requests.get(
                f"https://connect.linux.do/api/key?api_key={api_key}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                user_data = response.json()
                if user_data and "user_id" in user_data:
                    logger.info(f"LinuxDo认证成功，用户ID: {user_data.get('user_id')}")
                else:
                    raise ToolProviderCredentialValidationError("API Key验证失败：返回数据格式错误")
            elif response.status_code == 401:
                raise ToolProviderCredentialValidationError("认证失败：Client ID或Client Secret错误")
            elif response.status_code == 403:
                raise ToolProviderCredentialValidationError("API Key无效或已过期")
            else:
                raise ToolProviderCredentialValidationError(f"验证失败：HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            raise ToolProviderCredentialValidationError("连接超时：请检查网络连接")
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"网络请求失败：{str(e)}")
        except Exception as e:
            logger.exception(f"LinuxDo认证验证失败：{e}")
            raise ToolProviderCredentialValidationError(f"认证验证失败：{str(e)}")

    #########################################################################################
    # If OAuth is supported, uncomment the following functions.
    # Warning: please make sure that the sdk version is 0.4.2 or higher.
    #########################################################################################
    # def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
    #     """
    #     Generate the authorization URL for linuxdo OAuth.
    #     """
    #     try:
    #         """
    #         IMPLEMENT YOUR AUTHORIZATION URL GENERATION HERE
    #         """
    #     except Exception as e:
    #         raise ToolProviderOAuthError(str(e))
    #     return ""
        
    # def _oauth_get_credentials(
    #     self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    # ) -> Mapping[str, Any]:
    #     """
    #     Exchange code for access_token.
    #     """
    #     try:
    #         """
    #         IMPLEMENT YOUR CREDENTIALS EXCHANGE HERE
    #         """
    #     except Exception as e:
    #         raise ToolProviderOAuthError(str(e))
    #     return dict()

    # def _oauth_refresh_credentials(
    #     self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    # ) -> OAuthCredentials:
    #     """
    #     Refresh the credentials
    #     """
    #     return OAuthCredentials(credentials=credentials, expires_at=-1)
