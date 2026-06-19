# AI/ML API

AI/ML API provides OpenAI-compatible access to multiple chat model families through a single API key.

## Configuration

1. Create an API key at https://aimlapi.com/app/keys.
2. Add the AI/ML API provider in Dify.
3. Paste your API key.
4. Select a predefined chat model or add a custom OpenAI-compatible model ID.

The provider uses this fixed endpoint:

```text
https://api.aimlapi.com/v1
```

## Included models

The first version includes a curated starter set of chat models only:

- `openai/gpt-4o-mini`
- `openai/gpt-4o`
- `openai/gpt-5-chat-latest`
- `anthropic/claude-sonnet-4.6`
- `google/gemini-2.5-flash`

Embeddings, audio, video, and image generation are intentionally out of scope for this initial provider.
