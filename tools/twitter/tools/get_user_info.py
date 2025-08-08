import json
import requests
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetUserInfoTool(Tool):
    """
    Tool for getting user information from Twitter
    """
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get user information from Twitter
        """
        username = tool_parameters.get("username", "").strip()
        user_id = tool_parameters.get("user_id", "").strip()
        
        if not username and not user_id:
            yield self.create_text_message("Either username or user_id is required")
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
            
            # Prepare the API endpoint and parameters
            if user_id:
                url = f"https://api.twitter.com/2/users/{user_id}"
            else:
                url = f"https://api.twitter.com/2/users/by/username/{username}"
            
            # Add expanded user fields
            params = {
                "user.fields": "id,name,username,created_at,description,location,pinned_tweet_id,profile_image_url,protected,public_metrics,url,verified,verified_type"
            }
            
            # Make the API request
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                user_data = result["data"]
                
                # Extract user information
                user_info = {
                    "id": user_data.get("id"),
                    "name": user_data.get("name"),
                    "username": user_data.get("username"),
                    "description": user_data.get("description", ""),
                    "location": user_data.get("location", ""),
                    "created_at": user_data.get("created_at"),
                    "profile_image_url": user_data.get("profile_image_url"),
                    "url": user_data.get("url"),
                    "verified": user_data.get("verified", False),
                    "verified_type": user_data.get("verified_type"),
                    "protected": user_data.get("protected", False),
                    "pinned_tweet_id": user_data.get("pinned_tweet_id")
                }
                
                # Add public metrics if available
                if "public_metrics" in user_data:
                    metrics = user_data["public_metrics"]
                    user_info.update({
                        "followers_count": metrics.get("followers_count", 0),
                        "following_count": metrics.get("following_count", 0),
                        "tweet_count": metrics.get("tweet_count", 0),
                        "listed_count": metrics.get("listed_count", 0),
                        "like_count": metrics.get("like_count", 0)
                    })
                
                yield self.create_json_message(user_info)
                
                # Create a formatted text message
                text_info = f"""
User Information:
• Name: {user_info['name']}
• Username: @{user_info['username']}
• ID: {user_info['id']}
• Description: {user_info['description'][:100]}{'...' if len(user_info.get('description', '')) > 100 else ''}
• Location: {user_info['location']}
• Followers: {user_info.get('followers_count', 'N/A')}
• Following: {user_info.get('following_count', 'N/A')}
• Tweets: {user_info.get('tweet_count', 'N/A')}
• Verified: {'✓' if user_info['verified'] else '✗'}
• Protected: {'Yes' if user_info['protected'] else 'No'}
• Created: {user_info['created_at']}
"""
                
                yield self.create_text_message(text_info.strip())
                
                # Add profile link
                profile_url = f"https://twitter.com/{user_info['username']}"
                yield self.create_link_message(profile_url)
                
            else:
                error_data = response.json()
                error_message = error_data.get("detail", "Unknown error occurred")
                
                # Check for specific error cases
                if response.status_code == 404:
                    error_message = "User not found"
                elif response.status_code == 403:
                    error_message = "User account is suspended or protected"
                
                yield self.create_json_message({
                    "success": False,
                    "error": error_message,
                    "status_code": response.status_code
                })
                
                yield self.create_text_message(f"Failed to get user information: {error_message}")
                
        except Exception as e:
            yield self.create_text_message(f"Error getting user information: {str(e)}")