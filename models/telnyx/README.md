# Telnyx Model Provider

This plugin adds Telnyx AI model support for Dify.

Supported model types:

- LLM chat completions via `POST /v2/ai/chat/completions`
- Text embeddings via `POST /v2/ai/openai/embeddings`
- Text-to-speech via `POST /v2/text-to-speech/speech`
- Speech-to-text via `POST /v2/ai/audio/transcriptions`

Configure the provider with a Telnyx API key. The default API base is `https://api.telnyx.com`; override `telnyx_api_base` only when using a compatible proxy.
