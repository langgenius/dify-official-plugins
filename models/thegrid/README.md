# Overview

The Grid is an inference marketplace that serves models from several labs behind one OpenAI-compatible API. Instruments address a capability tier rather than a specific lab's model name — `text-standard`, `code-prime` and `agent-max` each route to a current model for that tier — so an app keeps working when the underlying model is replaced.

This plugin exposes The Grid's LLM instruments, including tool calling and streaming.

# Configure

After installation, get an API key from [The Grid](https://thegrid.ai/docs) and set it up in **Settings → Model Provider**.

The API Base URL is optional and defaults to `https://api.thegrid.ai/v1`.

# Models

Instruments come in capability tiers (`standard`, `prime`, `max`) across text, code and agent families, plus lab-pinned entries such as `claude-opus-latest` and `gemini-pro-latest`. `GET https://api.thegrid.ai/v1/models` returns the authoritative list.

Instruments reason before answering. Reasoning tokens are billed and count toward `max_tokens`, so leave headroom above the response length you expect. `reasoning_effort` controls how much reasoning is performed.
