from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetAccountInformationTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get account information from APITemplate.io
        """
        try:
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                yield self.create_text_message("APITemplate.io API key is not configured.")
                return
            
            # Prepare API request
            headers = {
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            }
            
            # Make API request
            response = requests.get(
                "https://rest.apitemplate.io/v2/account-information",
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = f"API Error: {error_data['message']}"
                except:
                    error_msg = f"API request failed with status {response.status_code}: {response.text}"
                
                yield self.create_text_message(error_msg)
                return
            
            # Parse response
            result = response.json()
            
            if result.get("status") != "success":
                error_msg = result.get("message", "Unknown error occurred")
                yield self.create_text_message(f"Failed to get account information: {error_msg}")
                return
            
            # Extract account information
            account_data = result.get("data", {})
            total_quota = account_data.get("total_quota", 0)
            quota_used = account_data.get("quota_used", 0)
            quota_available = total_quota - quota_used
            subscription_tier = account_data.get("subscription_tier", "Unknown")
            
            # Create success response
            summary = f"Account Information Retrieved:\n"
            summary += f"• Subscription Tier: {subscription_tier}\n"
            summary += f"• Total Quota: {total_quota}\n"
            summary += f"• Used: {quota_used}\n"
            summary += f"• Available: {quota_available}"
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "account_data": account_data,
                "quota_summary": {
                    "total_quota": total_quota,
                    "quota_used": quota_used,
                    "quota_available": quota_available,
                    "subscription_tier": subscription_tier
                }
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 