import json
import requests
from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendTweetTool(Tool):
    """
    Tool for sending tweets to Twitter
    """
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Send a tweet to Twitter
        """
        text = tool_parameters.get("text", "").strip()
        reply_to_tweet_id = tool_parameters.get("reply_to_tweet_id", "").strip()
        
        if not text:
            yield self.create_text_message("Tweet text is required")
            return
            
        if len(text) > 280:
            yield self.create_text_message("Tweet text exceeds 280 characters limit")
            return

        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Twitter Bearer Token is required")
            return

        try:
            # Prepare the tweet data
            tweet_data = {"text": text}
            
            # Add reply information if provided
            if reply_to_tweet_id:
                tweet_data["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
            
            # Set up headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            # Make the API request
            response = requests.post(
                "https://api.twitter.com/2/tweets",
                headers=headers,
                json=tweet_data,
                timeout=30
            )
            
            if response.status_code == 201:
                result = response.json()
                tweet_id = result["data"]["id"]
                tweet_text = result["data"]["text"]
                
                yield self.create_json_message({
                    "success": True,
                    "tweet_id": tweet_id,
                    "text": tweet_text,
                    "url": f"https://twitter.com/user/status/{tweet_id}"
                })
                
                yield self.create_text_message(f"Tweet sent successfully! Tweet ID: {tweet_id}")
                yield self.create_link_message(f"https://twitter.com/user/status/{tweet_id}")
                
            else:
                error_data = response.json()
                error_message = error_data.get("detail", "Unknown error occurred")
                
                yield self.create_json_message({
                    "success": False,
                    "error": error_message,
                    "status_code": response.status_code
                })
                
                yield self.create_text_message(f"Failed to send tweet: {error_message}")
                
        except Exception as e:
            yield self.create_text_message(f"Error sending tweet: {str(e)}")