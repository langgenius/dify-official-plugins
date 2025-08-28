# LinuxDo Connect Plugin for Dify

**Author:** frederick  
**Version:** 0.0.1  
**Type:** Tool Plugin

## Overview

The LinuxDo Connect plugin allows you to directly connect and interact with the LinuxDo forum within Dify. Through the LinuxDo Connect API, you can perform authentication, retrieve user information, search content, get personalized recommendations, and execute automatic check-ins.

## Features

### 🔐 User Authentication & Information
- Validate API key status
- Retrieve detailed user information (username, trust level, active status, etc.)
- Support for quick verification mode

### 🔍 Content Search
- Site-wide content search (topics, posts, categories)
- Advanced filtering options (category filtering, result sorting)
- Sort by relevance, date, views, or reply count
- Customizable result limit

## Installation & Configuration

### 1. Get LinuxDo Connect API Credentials

Visit [LinuxDo Connect](https://connect.linux.do) to apply for API access:

1. **Register Application**
   - Visit https://connect.linux.do
   - Click "My App Integration" -> "Apply for New Integration"
   - Fill in application information and callback URL

2. **Get Credentials**
   - **Client ID**: Client identifier for basic authentication
   - **Client Secret**: Client secret for basic authentication  
   - **API Key**: API key for user account identification

### 2. Configure Plugin in Dify

1. Install the LinuxDo Connect plugin in Dify
2. Fill in the obtained credentials in the plugin configuration page:
   - **Client ID**: Your LinuxDo Client ID
   - **Client Secret**: Your LinuxDo Client Secret
   - **API Key**: Your LinuxDo API Key

## Usage

### User Information

```python
# Get complete user information
user_info = linuxdo_user_info(
    include_extra_info=True,
    verify_only=False
)

# Only verify API Key status (faster)
verification = linuxdo_user_info(
    include_extra_info=False,
    verify_only=True
)
```

### Content Search

```python
# Search all content
search_results = linuxdo_content_search(
    search_query="Python programming",
    search_type="all",
    limit=20,
    sort_by="relevance"
)

# Search topics only
topic_results = linuxdo_content_search(
    search_query="machine learning",
    search_type="topics",
    category_filter="Technical Discussion",
    limit=10,
    sort_by="date"
)
```

## API Endpoints

### LinuxDo Connect API Endpoints
- **Authorization Endpoint**: `https://connect.linux.do/oauth2/authorize`
- **Token Endpoint**: `https://connect.linux.do/oauth2/token`  
- **User Info Endpoint**: `https://connect.linux.do/api/user`
- **User Info Endpoint (OAuth2)**: `https://connect.linux.do/oauth2/userinfo`

### Available User Fields
| Field | Description |
|-------|-------------|
| `id` | Unique user identifier (immutable) |
| `username` | Forum username |
| `name` | Forum display name (mutable) |
| `avatar_template` | User avatar template URL |
| `active` | Account active status |
| `trust_level` | Trust level (0-4) |
| `silenced` | Silenced status |
| `external_ids` | External ID associations |
| `api_key` | API access key |

## Data Structures

### User Info Response
```json
{
  "user_info": {
    "user_id": "string",
    "api_key_valid": true,
    "username": "string",
    "name": "string", 
    "trust_level": 0,
    "active": true,
    "admin": false,
    "moderator": false,
    "created_at": "2024-01-01T00:00:00Z",
    "last_seen_at": "2024-01-01T00:00:00Z"
  },
  "verification_result": {
    "status": "success",
    "user_id": "string",
    "api_key_valid": true,
    "message": "string"
  }
}
```

### Search Results Response
```json
{
  "search_results": [
    {
      "id": "string",
      "title": "string",
      "content": "string",
      "author": "string",
      "category": "string", 
      "url": "string",
      "created_at": "2024-01-01T00:00:00Z",
      "views": 0,
      "replies": 0,
      "relevance_score": 0.95
    }
  ],
  "search_summary": {
    "total_results": 0,
    "search_query": "string",
    "search_type": "string",
    "processing_time": 0.5,
    "filters_applied": ["string"]
  }
}
```

## Security Recommendations

1. **Protect Credentials**
   - Keep Client Secret and API Key secure
   - Never expose sensitive information in frontend code
   - Regularly update API credentials

2. **Network Security**  
   - Ensure HTTPS protocol for data transmission
   - Validate all user input data

3. **Access Control**
   - Implement service restrictions based on user trust level
   - Monitor API usage frequency to prevent abuse

## Troubleshooting

### Common Issues

**Q: API Key validation failed**  
A: Please check the following:
- Confirm API Key format is correct
- Verify Client ID and Client Secret match
- Check network connection is stable

**Q: Empty search results**  
A: Possible causes:
- Search keywords too specific
- Category filtering too strict
- Try adjusting search parameters or using more general keywords

## Development Information

### Dependencies
- `dify_plugin>=0.2.0,<0.3.0`
- `requests>=2.31.0`

### Project Structure
```
linuxdo/
├── manifest.yaml              # Plugin manifest file
├── requirements.txt           # Python dependencies
├── main.py                   # Plugin entry point
├── provider/
│   ├── linuxdo.py           # Provider implementation
│   └── linuxdo.yaml         # Provider configuration
├── tools/
│   ├── linuxdo.py           # User info tool
│   ├── linuxdo.yaml         # User info tool configuration
│   ├── content_search.py    # Content search tool
│   └── content_search.yaml  # Content search tool configuration
└── _assets/
    ├── icon.svg            # Plugin icon
    └── icon-dark.svg       # Dark mode icon
```

## License

This plugin follows the corresponding open source license. Please ensure compliance with LinuxDo forum terms of use and API usage policies before use.

## Support & Feedback

For questions or suggestions, please contact us through:
- Create a GitHub Issue  
- Contact the author on LinuxDo forum
- Send email to the developer

---

**Note**: Using this plugin requires a valid LinuxDo account and Connect API access permissions. Please ensure compliance with forum usage rules and API usage restrictions.
