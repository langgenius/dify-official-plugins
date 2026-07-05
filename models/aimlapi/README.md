# AI/ML API

Dify model provider plugin for [AI/ML API](https://aimlapi.com/).

AI/ML API exposes an OpenAI-compatible chat completions endpoint at
`https://api.aimlapi.com/v1` and authenticates with a bearer token. This
plugin wraps that endpoint so Dify apps can select AI/ML API models through
the standard model picker.

## Prerequisites

- A Dify installation with custom model providers enabled.
- An AI/ML API account and API key — get one at
  [https://aimlapi.com/app/keys](https://aimlapi.com/app/keys).

## Install

1. Install this plugin from the marketplace (or via the offline package
   workflow).
2. In Dify, open **Settings → Model Providers** and add **AI/ML API**.
3. Paste your API key. The endpoint URL is pre-filled with
   `https://api.aimlapi.com/v1`; override it only if AI/ML API publishes a
   new base URL.
4. Save and verify with the built-in credential validation.

## Add a model

1. Open the AI/ML API provider config in Dify.
2. Click **Add Model** and supply the AI/ML API model id, for example
   `openai/gpt-4o-mini` or `anthropic/claude-3-5-sonnet`.
3. Pick the completion mode (`chat` is the common choice), set the model
   context size, and save.

The AI/ML API model catalog is published at
[https://aimlapi.com/models](https://aimlapi.com/models). Use the exact
model id from the catalog.

## Scope

This first release covers **LLM (chat completions) only**. Embeddings,
speech, image generation, and other modalities are not exposed yet and will
land in follow-up PRs.

## Verification

The provider reuses the official
`OAICompatLargeLanguageModel` from `dify_plugin`, so streaming, function
calling, and structured-output behavior match the OpenAI-compatible plugin.
Dify's per-model credential validation issues a minimal chat request against
the configured endpoint and rejects the credentials on a non-2xx response.