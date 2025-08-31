import json
import requests
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteTweetTool(Tool):
    """
    Tool for deleting tweets on Twitter
    """
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a tweet on Twitter
        """
        tweet_id = tool_parameters.get("tweet_id", "").strip()
        
        if not tweet_id:
            yield self.create_text_message("Tweet ID is required")
            return

        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Twitter Bearer Token is required")
            return

        try:
            # Set up headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            # Make the API request to delete the tweet
            response = requests.delete(
                f"https://api.twitter.com/2/tweets/{tweet_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                deleted = result["data"]["deleted"]
                
                if deleted:
                    yield self.create_json_message({
                        "success": True,
                        "tweet_id": tweet_id,
                        "deleted": True,
                        "message": "Tweet deleted successfully"
                    })
                    
                    yield self.create_text_message(f"Tweet {tweet_id} deleted successfully!")
                else:
                    yield self.create_json_message({
                        "success": False,
                        "tweet_id": tweet_id,
                        "deleted": False,
                        "message": "Failed to delete tweet"
                    })
                    
                    yield self.create_text_message(f"Failed to delete tweet {tweet_id}")
                    
            else:
                error_data = response.json()
                error_message = error_data.get("detail", "Unknown error occurred")
                
                # Check for specific error cases
                if response.status_code == 403:
                    error_message = "You can only delete your own tweets"
                elif response.status_code == 404:
                    error_message = "Tweet not found or already deleted"
                
                yield self.create_json_message({
                    "success": False,
                    "tweet_id": tweet_id,
                    "error": error_message,
                    "status_code": response.status_code
                })
                
                yield self.create_text_message(f"Failed to delete tweet: {error_message}")
                
        except Exception as e:
            yield self.create_text_message(f"Error deleting tweet: {str(e)}")