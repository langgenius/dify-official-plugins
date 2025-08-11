import datetime
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class GetTopStoriesTool(Tool):
    """
    Tool for retrieving Hacker News top stories.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get top stories from Hacker News.
        """
        # Extract parameters
        limit = tool_parameters.get("limit", 10)
        story_type = tool_parameters.get("story_type", "top")
        include_content = tool_parameters.get("include_content", False)

        try:
            limit = int(limit)
            if limit < 1 or limit > 30:
                yield self.create_text_message("Limit must be between 1 and 30")
                return
        except ValueError:
            yield self.create_text_message("Limit must be a valid number")
            return

        try:
            # Log the operation start
            yield self.create_log_message(
                label="Fetching Top Stories",
                data={"limit": limit, "story_type": story_type},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Determine API endpoint based on story type
            if story_type == "top":
                api_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
            elif story_type == "new":
                api_url = "https://hacker-news.firebaseio.com/v0/newstories.json"
            elif story_type == "best":
                api_url = "https://hacker-news.firebaseio.com/v0/beststories.json"
            elif story_type == "ask":
                api_url = "https://hacker-news.firebaseio.com/v0/askstories.json"
            elif story_type == "show":
                api_url = "https://hacker-news.firebaseio.com/v0/showstories.json"
            elif story_type == "job":
                api_url = "https://hacker-news.firebaseio.com/v0/jobstories.json"
            else:
                api_url = "https://hacker-news.firebaseio.com/v0/topstories.json"

            # Get story IDs
            response = requests.get(api_url, timeout=10)
            if response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to fetch stories. HTTP {response.status_code}"
                )
                return

            story_ids = response.json()[:limit]

            if not story_ids:
                yield self.create_text_message("No stories found")
                return

            # Fetch story details
            stories = []
            failed_fetches = 0

            for i, story_id in enumerate(story_ids):
                try:
                    # Show progress
                    if i % 5 == 0:
                        yield self.create_log_message(
                            label=f"Fetching Story {i+1}/{len(story_ids)}",
                            data={"story_id": story_id},
                            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                        )

                    story_response = requests.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                        timeout=8,
                    )
                    if story_response.status_code == 200:
                        story_data = story_response.json()
                        if story_data:
                            # Format story data
                            created_date = "N/A"
                            if story_data.get("time"):
                                created_date = datetime.datetime.fromtimestamp(
                                    story_data["time"]
                                ).strftime("%Y-%m-%d %H:%M")

                            story_info = {
                                "id": story_data.get("id"),
                                "title": story_data.get("title", "No title"),
                                "author": story_data.get("by", "Unknown"),
                                "score": story_data.get("score", 0),
                                "created": created_date,
                                "url": story_data.get("url", ""),
                                "type": story_data.get("type", "story"),
                                "descendants": story_data.get("descendants", 0),
                                "text": story_data.get("text", ""),
                            }

                            # Extract content if requested
                            if include_content and story_info["url"]:
                                try:
                                    import re

                                    content_response = requests.get(
                                        story_info["url"],
                                        timeout=10,
                                        headers={
                                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                                        },
                                    )
                                    if content_response.status_code == 200:
                                        content = content_response.text
                                        content = re.sub(r"<[^>]+>", " ", content)
                                        content = re.sub(r"\s+", " ", content).strip()
                                        story_info["content"] = (
                                            content[:500] + "..."
                                            if len(content) > 500
                                            else content
                                        )
                                except:
                                    story_info["content"] = "Content extraction failed"
                            elif include_content and story_info["text"]:
                                import re

                                content = re.sub(r"<[^>]+>", " ", story_info["text"])
                                story_info["content"] = re.sub(
                                    r"\s+", " ", content
                                ).strip()
                            elif include_content:
                                story_info["content"] = "No content available"

                            stories.append(story_info)
                    else:
                        failed_fetches += 1
                except:
                    failed_fetches += 1
                    continue

            if not stories:
                yield self.create_text_message("Failed to fetch any story details")
                return

            # Create formatted text response
            story_type_label = {
                "top": "Top Stories",
                "new": "New Stories",
                "best": "Best Stories",
                "ask": "Ask HN",
                "show": "Show HN",
                "job": "Job Posts",
            }.get(story_type, "Stories")

            text_response = f"**Hacker News {story_type_label}**\n\n"

            for i, story in enumerate(stories, 1):
                text_response += f"**{i}. {story['title']}**\n"
                text_response += f"   • ID: {story['id']} | Score: {story['score']} | Comments: {story['descendants']}\n"
                text_response += (
                    f"   • By: {story['author']} | Posted: {story['created']}\n"
                )
                if story["url"]:
                    text_response += f"   • URL: {story['url']}\n"
                if include_content and story.get("content"):
                    text_response += f"   • Content: {story['content'][:200]}{'...' if len(story.get('content', '')) > 200 else ''}\n"
                text_response += "\n"

            if failed_fetches > 0:
                text_response += (
                    f"\n*Note: Failed to fetch details for {failed_fetches} stories*"
                )

            yield self.create_text_message(text_response)
            yield self.create_json_message(
                {
                    "story_type": story_type,
                    "total_fetched": len(stories),
                    "failed_fetches": failed_fetches,
                    "stories": stories,
                }
            )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
