# API Route for Dify

Use an [API Route](https://www.api-route.com/) API key to access multiple models from Dify through the OpenAI-compatible API.

## Setup

1. Create an API key in API Route.
2. Install this plugin and open **Settings → Model Providers → API Route** in Dify.
3. Enter the key. The default API base URL is `https://global.api-route.com/v1`.
4. Select one of the included models or add any currently available model by its exact ID.

The included model list is deliberately small; availability and prices can change. Check the [current API Route model catalog](https://www.api-route.com/pricing) before selecting a model. Custom models use a conservative default context size of 32,768 tokens; set their limits to match the model and route you use.

The plugin uses Dify's OpenAI-compatible chat implementation for streaming and tool calls. It has no separate account or API key; all requests go directly to API Route.

## Development

The plugin requires Python 3.12 and `dify_plugin`. Run `uv sync` in this directory to install its dependencies. Live credential and response checks require an API Route key and funded account.
