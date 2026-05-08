# Telnyx Model Provider

This plugin adds Telnyx AI model support for Dify.

Supported model types:

- LLM chat completions via `POST /v2/ai/chat/completions`
- Text embeddings via `POST /v2/ai/openai/embeddings`
- Text-to-speech via `POST /v2/text-to-speech/speech`
- Speech-to-text via `POST /v2/ai/audio/transcriptions`

Configure the provider with a Telnyx API key. The default API base is `https://api.telnyx.com`; override `telnyx_api_base` only when using a compatible proxy.

The predefined model YAMLs are aligned with Telnyx's official docs and the live `/v2/ai/openai/models` and `/v2/ai/openai/embeddings/models` model-list endpoints. Telnyx REST TTS docs and examples have some path ambiguity; this provider keeps using `POST /v2/text-to-speech/speech`, which is the endpoint verified by the live provider smoke tests.
