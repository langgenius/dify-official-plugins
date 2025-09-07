# Regolo.ai – Guide

## Credentials

- `regolo_api_key`: API key from Regolo dashboard
- `endpoint_url` (optional): default `https://api.regolo.ai/v1`

## Supported Models

- LLM: deepseek-r1-70b, gemma-3-27b-it, gpt-oss-120b, Llama-3.1-8B-Instruct, Llama-3.3-70B-Instruct, maestrale-chat-v0.4-beta, mistral-small3.2, Phi-4, Qwen2.5-VL-32B-Instruct, Qwen3-8B, qwen3-coder-30b, llama-guard3-8b
- Embedding: gte-Qwen2, Qwen3-Embedding-8B

## Pricing

- Our price use `unit: 0.000001` (per 1M tokens).

## Operational Notes

- Streaming is automatically disabled for `gpt-oss-120b` to avoid a LiteLLM parser issue.

## Troubleshooting

- 401: check key, endpoint, and try curl.
- Context window: reduce prompt or `max_tokens`.
