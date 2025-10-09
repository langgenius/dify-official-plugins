import requests
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class LikeTweetTool(Tool):
    """
    Tool for liking tweets on Twitter
    """
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Like a tweet on Twitter
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
            # First, get current user ID
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            # Get user info to obtain user ID
            user_response = requests.get(
                "https://api.twitter.com/2/users/me",
                headers=headers,
                timeout=30
            )
            
            if user_response.status_code != 200:
                yield self.create_text_message("Failed to get user information")
                return
                
            user_data = user_response.json()
            user_id = user_data["data"]["id"]

            # Prepare the like data
            like_data = {"tweet_id": tweet_id}
            
            # Make the API request to like the tweet
            response = requests.post(
                f"https://api.x.com/2/users/{user_id}/likes",
                headers=headers,
                json=like_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                liked = result["data"]["liked"]
                
                if liked:
                    yield self.create_json_message({
                        "success": True,
                        "tweet_id": tweet_id,
                        "liked": True,
                        "message": "Tweet liked successfully"
                    })
                    
                    yield self.create_text_message(f"Tweet {tweet_id} liked successfully!")
                else:
                    yield self.create_text_message(f"Failed to like tweet {tweet_id}")
                    
            else:
                error_data = response.json()
                error_message = error_data.get("detail", "Unknown error occurred")
                
                yield self.create_json_message({
                    "success": False,
                    "tweet_id": tweet_id,
                    "error": error_message,
                    "status_code": response.status_code
                })
                
                yield self.create_text_message(f"Failed to like tweet: {error_message}")
                
        except Exception as e:
            yield self.create_text_message(f"Error liking tweet: {str(e)}")