import re
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class GetStoryInfoTool(Tool):
    """
    Tool for retrieving Hacker News story information including content.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get Hacker News story information by ID, including content extraction.
        """
        # Extract parameters
        story_id = tool_parameters.get("story_id")
        include_comments = tool_parameters.get("include_comments", False)
        max_comments = tool_parameters.get("max_comments", 5)

        if not story_id:
            yield self.create_text_message("Story ID is required")
            return

        try:
            # Convert to int if it's a string
            story_id = int(story_id)
        except ValueError:
            yield self.create_text_message("Story ID must be a valid number")
            return

        try:
            # Log the operation start
            yield self.create_log_message(
                label="Fetching Story Info",
                data={"story_id": story_id, "include_comments": include_comments},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Make API call to get story info
            api_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
            response = requests.get(api_url, timeout=10)

            if response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to fetch story. HTTP {response.status_code}"
                )
                return

            story_data = response.json()

            if not story_data:
                yield self.create_text_message(f"Story with ID {story_id} not found")
                return

            # Check if it's actually a story
            if story_data.get("type") not in ["story", "job", "poll"]:
                yield self.create_text_message(
                    f"Item {story_id} is not a story (type: {story_data.get('type', 'unknown')})"
                )
                return

            # Extract story content
            story_content = ""
            story_url = story_data.get("url", "")

            # If there's a URL, try to extract content
            if story_url:
                try:
                    content_response = requests.get(
                        story_url,
                        timeout=15,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        },
                    )
                    if content_response.status_code == 200:
                        # Simple content extraction - remove HTML tags and get first few paragraphs
                        content = content_response.text
                        # Remove HTML tags
                        content = re.sub(r"<[^>]+>", " ", content)
                        # Remove extra whitespace
                        content = re.sub(r"\s+", " ", content).strip()
                        # Get first 1000 characters as content preview
                        if len(content) > 1000:
                            story_content = content[:1000] + "..."
                        else:
                            story_content = content
                except:
                    story_content = "Content could not be extracted from the linked URL"

            # If no URL or content extraction failed, use the story text
            if not story_content and story_data.get("text"):
                # Remove HTML tags from story text
                story_content = re.sub(r"<[^>]+>", " ", story_data.get("text", ""))
                story_content = re.sub(r"\s+", " ", story_content).strip()

            # Format story information
            import datetime

            created_date = "N/A"
            if story_data.get("time"):
                created_date = datetime.datetime.fromtimestamp(
                    story_data["time"]
                ).strftime("%Y-%m-%d %H:%M:%S")

            story_info = {
                "id": story_data.get("id"),
                "title": story_data.get("title", "No title"),
                "author": story_data.get("by", "Unknown"),
                "score": story_data.get("score", 0),
                "time": story_data.get("time"),
                "created": created_date,
                "url": story_url,
                "text": story_data.get("text", ""),
                "content": story_content,
                "type": story_data.get("type"),
                "descendants": story_data.get("descendants", 0),
                "kids": story_data.get("kids", []),
            }

            # Create formatted text response
            text_response = f"""**{story_info['title']}**

**Story Details:**
- ID: {story_info['id']}
- Author: {story_info['author']}
- Score: {story_info['score']} points
- Comments: {story_info['descendants']}
- Posted: {story_info['created']}
- Type: {story_info['type']}

**URL:** {story_info['url'] if story_info['url'] else 'No external URL'}

**Content:**
{story_info['content'] if story_info['content'] else 'No content available'}
"""

            # Add comments if requested
            if include_comments and story_info["kids"]:
                text_response += "\n\n**Top Comments:**\n"
                comments = self._get_comments(story_info["kids"][:max_comments])
                for i, comment in enumerate(comments, 1):
                    if comment:
                        text_response += f"\n{i}. **{comment.get('author', 'Unknown')}** ({comment.get('score', 0)} points):\n"
                        text_response += f"   {comment.get('text', 'No text')}\n"

            yield self.create_text_message(text_response)
            yield self.create_json_message(story_info)

            # If there's an external URL, provide it as a link
            if story_url:
                yield self.create_link_message(story_url)

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

    def _get_comments(self, comment_ids: list) -> list:
        """Helper method to fetch comment details."""
        comments = []
        for comment_id in comment_ids:
            try:
                response = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json",
                    timeout=5,
                )
                if response.status_code == 200:
                    comment_data = response.json()
                    if comment_data and comment_data.get("type") == "comment":
                        # Remove HTML tags from comment text
                        comment_text = comment_data.get("text", "")
                        if comment_text:
                            comment_text = re.sub(r"<[^>]+>", " ", comment_text)
                            comment_text = re.sub(r"\s+", " ", comment_text).strip()
                            # Limit comment length
                            if len(comment_text) > 200:
                                comment_text = comment_text[:200] + "..."

                        comments.append(
                            {
                                "id": comment_data.get("id"),
                                "author": comment_data.get("by", "Unknown"),
                                "score": comment_data.get("score", 0),
                                "text": comment_text,
                            }
                        )
            except:
                continue
        return comments
