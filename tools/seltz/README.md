# Seltz

Seltz is a Web Knowledge API for AI Agents — a fast, real-time web knowledge API built for AI agents, LLMs, and RAG systems, delivering context-engineered web content for smarter reasoning and decisions.

## Features

- **Real-Time Web Knowledge**: Access up-to-date web content optimized for AI consumption
- **Built for AI Agents**: Context-engineered responses designed for LLMs and RAG systems
- **Simple Integration**: Easy-to-use search functionality for agents and workflows
- **Configurable Results**: Control the number of documents returned

## Configuration

### Getting Your API Key

1. Sign up for a Seltz account on the Seltz console: https://console.seltz.ai
2. Navigate to "API Keys" and click on "Create" to generate a new API key
3. Copy your API key

### Plugin Setup

1. Install the Seltz plugin in Dify
2. Configure the plugin with your API key:
   - **API Key** (required): Your Seltz API key

## Usage

### In Agents

The Seltz Search tool can be used by agents to search for relevant information:

```
Search for information about machine learning best practices
```

### In Workflows

Add the Seltz Search node to your workflow and configure:

- **Search Query**: The text to search for
- **Max Documents**: Maximum number of documents to return (default: 10)

## Tool Parameters

| Parameter     | Type   | Required | Default | Description                 |
| ------------- | ------ | -------- | ------- | --------------------------- |
| query         | string | Yes      | -       | The search query text       |
| max_documents | number | No       | 10      | Maximum documents to return |

## Output

Each search result contains:

- `url`: The URL of the source document
- `content`: The relevant content from the document

## Error Handling

The plugin handles various error scenarios:

- **Configuration Error**: Invalid plugin configuration
- **Authentication Error**: Invalid or missing API key
- **Connection Error**: Unable to reach the Seltz API
- **Timeout Error**: Request took too long
- **Rate Limit Error**: Too many requests
- **API Error**: General API errors

## Requirements

- Python 3.12+
- Dify Plugin SDK >= 0.3.0
- Seltz Python SDK

## Example SDK Usage

```python
from seltz import Seltz

# Initialize client
client = Seltz(api_key="your-api-key")

# Perform search
response = client.search(text="your query", max_documents=10)

# Access results
for doc in response.documents:
    print(f"URL: {doc.url}")
    print(f"Content: {doc.content}")
```

## Links

- [Dify Documentation](https://docs.dify.ai)
