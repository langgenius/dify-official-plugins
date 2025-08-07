# Hacker News Plugin

**Author**: langgenius  
**Version**: 0.1.0  
**Type**: tool  

## Introduction

This plugin provides seamless integration with Hacker News, enabling you to access stories, user information, and comments directly from your Dify applications. Retrieve trending stories, analyze user profiles, and get detailed story information without manual browsing.

## Features

- **No Authentication Required**: Access public Hacker News data instantly without setup
- **Multiple Story Types**: Fetch top, new, best, Ask HN, Show HN, and job stories
- **Content Extraction**: Automatically extract content from linked articles
- **User Information**: Get comprehensive user profiles and submission history
- **Batch Operations**: Retrieve multiple users or stories efficiently
- **Comment Integration**: Include top comments with story details

## Tool Descriptions

### get_top_stories
Retrieve a list of stories from Hacker News with various filtering options.

**Parameters:**
- `limit` (number, optional): Number of stories to retrieve (1-30, default: 10)
- `story_type` (string, optional): Type of stories to retrieve (default: "top")
  - `top`: Top Stories
  - `new`: New Stories  
  - `best`: Best Stories
  - `ask`: Ask HN
  - `show`: Show HN
  - `job`: Job Posts
- `include_content` (boolean, optional): Whether to extract and include article content (default: false)

**Returns:** List of stories with title, author, score, creation time, URL, and optionally extracted content.

### get_story_info
Get detailed information about a specific Hacker News story.

**Parameters:**
- `story_id` (string, required): The numerical ID of the Hacker News story
- `include_comments` (boolean, optional): Whether to include top comments (default: false)
- `max_comments` (number, optional): Maximum number of comments to include (1-20, default: 5)

**Returns:** Comprehensive story details including title, content, author, score, comments, and extracted article content.

### get_user_info
Retrieve detailed information about a Hacker News user.

**Parameters:**
- `username` (string, required): The Hacker News username to look up

**Returns:** User profile including username, creation date, karma score, bio, and recent submission history.

### get_multiple_users
Get information about multiple Hacker News users simultaneously.

**Parameters:**
- `usernames` (string, required): Comma-separated list of usernames (maximum 10)
- `include_submissions` (boolean, optional): Whether to include recent submission details (default: false)
- `max_submissions` (number, optional): Maximum submissions per user (1-10, default: 5)

**Returns:** Batch user information with profiles and optionally detailed submission data.

## Usage Examples

### Getting Top Stories
```
Get the top 5 stories from Hacker News with full content extraction
```

### Analyzing a Story
```
Get detailed information about story ID 12345 including the top 3 comments
```

### User Research
```
Get information about users: pg, sama, antirez including their recent submissions
```

### Monitoring New Content
```
Fetch the latest 10 new stories to stay updated with recent submissions
```

## Data Sources

This plugin uses the official [Hacker News API](https://github.com/HackerNews/API) to retrieve:
- Stories from all categories (top, new, best, ask, show, jobs)
- User profiles and submission history
- Comments and discussion threads
- Real-time content updates

## Privacy & Terms

This plugin accesses only publicly available data from Hacker News. No personal information or authentication is required. Please respect Hacker News' terms of service and rate limits when using this plugin extensively.

## Support

For issues, feature requests, or contributions, please refer to the main Dify plugins repository.

Last updated: Aug 2025
