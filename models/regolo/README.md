# Regolo.ai Model Provider

This plugin integrates Regolo.ai models into Dify as a Model Provider.

## Setup

1. Install the plugin (Marketplace or local).
2. In Dify Settings → Model Provider → Regolo.ai, fill in:
   - API Key: your Regolo API key
   - Endpoint URL (optional): defaults to `https://api.regolo.ai/v1`
3. Click Save. A quick credentials validation is performed.

## Supported Types

- LLM
- Text Embedding

## Pricing Convention

- All YAML use Dify pricing unit `unit: 0.000001` (per 1M tokens).

## Endpoints

- Default endpoint: `https://api.regolo.ai/v1`
- The provider normalizes custom URLs and ensures `/v1` is present.

## Notes

- For `gpt-oss-120b`, streaming is disabled to avoid a LiteLLM parsing issue.

## Troubleshooting

- 401 Auth Error: recheck API Key field (no spaces) and endpoint. A curl check can help:
  \`\`\`bash
  curl -H "Authorization: Bearer $REGOLO_API_KEY" https://api.regolo.ai/v1/models | cat
  \`\`\`
- ContextWindowExceededError: reduce prompt or `max_tokens`.

## Links

- Regolo website: https://regolo.ai/
