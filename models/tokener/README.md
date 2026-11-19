# Tokener.ai

## Configure

Tokener.ai provides language, text embedding, rerank, moderation, speech recognition, and text-to-speech models for Dify.

1. Install **Tokener.ai** from the Dify Marketplace.
2. Create an API key in the [Tokener.ai Console](https://console.tokener.ai/keys).
3. Open **Settings → Model Provider → Tokener.ai** and enter the key.

The API endpoint changes from `https://api.tokener.dev/v1` to `https://api.tokener.ai/v1`.
Existing keys from the same Tokener.ai Console remain valid. The API key must have access to the selected model.

In a Workflow or Chatflow, select Tokener.ai and a model in the corresponding node or model configuration.
Embedding models appear in the provider list after installation. Embeddings retain the selected model ID and default vector dimensions.
For `text-embedding-v3` and `text-embedding-v4`, the plugin sends up to 10 texts per request.
Both models accept up to 8192 tokens per text and retain the default 1024 vector dimensions.
Tongyi text embeddings truncate long inputs to the model context limit.
OpenAI embeddings split long inputs and normalize the combined vectors.
Other embedding models use up to 32 texts per request.
For `embed-english-v3`, `embed-multilingual-v3`, and `embed-v4`, the plugin sends `input_type=search_query` for queries and `input_type=search_document` for documents.
These models retain their default vector dimensions: 1024 for both v3 models and 1536 for v4.
For `gemini-embedding-2-preview`, the plugin adds Google's retrieval prefixes to distinguish queries from documents. This release keeps the same text prefixes as 0.4.4. Knowledge bases that already use those prefixes can keep their existing vectors. The following migration instructions apply to knowledge bases that still use embeddings from before 0.4.4.
Self-hosted administrators must clear document caches for provider `langgenius/tokener/tokener` and model `gemini-embedding-2-preview`. Also clear matching query caches: Redis prefix `langgenius/tokener/tokener_gemini-embedding-2-preview_`, prefixed with `REDIS_KEY_PREFIX` and a colon when configured. These caches are shared across knowledge bases.
Then, during low traffic, switch each affected knowledge base to another configured embedding model, then back. After each switch, wait for indexing and resolve document errors.
Each switch can incur embedding charges and causes empty, then partial retrieval results while applications continue running. Saving the same model does not rebuild. Failed documents are not retried automatically.
Dify Cloud users must contact support for cache cleanup before switching models. The retrieval-quality effect of mixing old and new vectors is unverified.
For `gemini-embedding-001`, the plugin uses native token counting and batch embedding requests.
It sends `taskType=RETRIEVAL_QUERY` for queries and `taskType=RETRIEVAL_DOCUMENT` for documents.
Long texts are split, then their vectors are combined and normalized.

Provider, LLM, and embedding validation use authenticated `GET /v1/models`.
Rerank and moderation validation send small requests. Speech validation sends demo audio or a short speech request.
These validation requests can incur charges.

## Model parameters

The generator reads family rules from `scripts/parameter_profiles.json` and capabilities from the catalog.
Model settings expose controls for the selected model family.
Unknown families expose the output limit and catalog-declared structured output controls.

GPT-4o-mini and its 2024-07-18 version expose temperature, top-p, presence penalty, and frequency penalty controls.
The Responses API rejects nonzero penalties and seed, as in the OpenAI source plugin.
For `glm-4.7`, `glm-4.7-flash`, `qwen3-coder-30b-a3b`, `qwen3-coder-next`, and `qwen3-vl-235b-a22b`, temperature ranges from 0 to 1.

OpenAI language models use the Responses API. The `gpt-audio-*` models use Chat Completions.
Claude uses the Messages API. Gemini uses GenerateContent, or Interactions when a supported model combines built-in tools with structured output.
Tongyi and xAI use Chat Completions with provider-specific options.
Catalog metadata does not describe deployment parameter overrides. Recheck the profiles when the upstream contract or deployment policy changes.

## Sync models

Run the generator from `models/tokener` with a complete Tokener catalog snapshot JSON file.
The snapshot must include restricted models available to your users. The public catalog hides restricted models.
An OpenAI `/v1/models` response lacks the context, capability, and price metadata needed for generation.

```bash
export UV_PROJECT_ENVIRONMENT=/tmp/tokener-plugin-venv
uv run --frozen python scripts/sync_catalog.py --input /tmp/tokener-models.json
uv run --frozen python scripts/sync_catalog.py --input /tmp/tokener-models.json --check
```

LLM generation also reads the five source providers in the sibling `models` directory.
Use `--source-root /path/to/models` for a separate checkout. Missing source providers
stop generation before any files are written. Source parameter rules and required
defaults take precedence over catalog parameter profiles.

The snapshot must contain the complete `items` array. Each item supplies `publicModelId`, `category`, `enabled`, `managedAvailable`, and model metadata.
The generator includes models with both `enabled: true` and `managedAvailable: true`, regardless of access scope.
Both display labels use the public model ID. Internal identifiers and display names are excluded.
Decision routes are outside the supported Dify model types. Unknown categories stop generation and identify the affected public model IDs.
Keep the source snapshot outside Git. The snapshot does not prove that a particular API key has model access.

The generator also accepts a complete machine catalog snapshot with `schemaVersion: 1`, `catalogRevision`, and `models`.
The input path is required. If the file contains an HTML login page, re-authenticate and obtain a new JSON snapshot.
Never put keys in snapshots or commits.

The default selection includes all six supported model types, including moderation.
Select `--model-type llm`, `text_embedding`, `rerank`, `tts`, `speech2text`, or `moderation` to update one type.
Synchronization validates all selected types before writing. It deletes model YAMLs that lack a matching snapshot entry in each selected type.
An empty type produces an empty position list and removes its model definitions. `--check` reports drift without writing.

Embedding prices use the catalog input price.
Rerank, moderation, and audio definitions omit optional Dify prices. Tokener.ai determines their charges.
LLM prices show the catalog base input and output rates. Dify's model definitions cannot represent cache read, cache write, or context-tier prices.
Tokener.ai determines charges. Audio models require complete voice or upload metadata and prices.
New audio models use their catalog type and metadata, without an ID allowlist.

## Audio behavior

Speech recognition uploads files to `/v1/audio/transcriptions`. Upload limits and extensions come from catalog metadata. Upload limits use decimal megabytes.
The diarization model uses automatic chunking and returns text without speaker labels.
Text-to-speech sends requests to `/v1/audio/speech`. Voices, languages, the default voice, text limits, and format come from catalog metadata.
Voice languages must use Dify UI locale codes. An unsupported code stops generation and identifies the model, voice, and code.

Long speech text is split into sequential requests. The text limit counts characters, as in the OpenAI plugin.
The plugin streams MP3, AAC, Opus, and PCM audio in order. A later failure raises an error after any audio already sent.
For WAV, the plugin combines PCM samples into one WAV file before sending audio. Qwen TTS uses WAV with a limit of 512 characters per request.
An empty stream raises an error.

Audio definitions appear only when the snapshot contains matching available models.
Dify playback and production latency remain unverified.
A segment without output for more than 120 seconds can exceed the serverless idle limit.

## Support

Open an issue in [dify-official-plugins](https://github.com/langgenius/dify-official-plugins/issues).
Include the Dify version, plugin version, model ID, and request ID. Never include API keys or prompt content.

Apache License 2.0. See [LICENSE](https://github.com/langgenius/dify-official-plugins/blob/main/LICENSE).
