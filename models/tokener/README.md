# Tokener.ai

## Configure

Tokener.ai provides language, text embedding, rerank, speech recognition, and text-to-speech models for Dify.

1. Install **Tokener.ai** from the Dify Marketplace.
2. Create an API key in the [Tokener.ai Console](https://console.tokener.ai/keys).
3. Open **Settings → Model Provider → Tokener.ai** and enter the key.

The API endpoint changes from `https://api.tokener.dev/v1` to `https://api.tokener.ai/v1`.
Existing keys from the same Tokener.ai Console remain valid. The API key must have access to the selected model.

In a Workflow or Chatflow, select Tokener.ai and a model in the corresponding node or model configuration.
Embedding models appear in the provider list after installation. Embeddings retain the selected model ID and default vector dimensions.
The plugin sends up to 32 texts per embedding request. It does not truncate texts.
For `gemini-embedding-2-preview`, the plugin adds Google's retrieval prefixes to distinguish queries from documents.
Existing knowledge indexes can mix prefixed queries with unprefixed document vectors after this update.
Rebuilding an index alone reuses cached document vectors without the prefix.
For self-hosted Dify, the document cache uses `provider_name = langgenius/tokener/tokener` and `model_name = gemini-embedding-2-preview`.
The query cache uses the logical Redis key prefix `langgenius/tokener/tokener_gemini-embedding-2-preview_`, followed by the text hash.
If `REDIS_KEY_PREFIX` is configured, physical Redis keys also start with its trimmed value and a colon.
These caches are shared across knowledge bases that use the same provider and model.
After all plugin instances use this version, schedule both model switches during a low-traffic period.
Applications continue running during each switch.
Knowledge retrieval first returns no results, then partial results as documents finish indexing.
An administrator must complete these steps for affected knowledge bases:

1. Clear document cache rows that match both `provider_name` and `model_name` above.
2. Clear query cache keys with the matching Redis prefix, including the deployment prefix when configured.
3. In each knowledge base, select another configured embedding model and save. Wait for indexing to finish. Check for documents with `error` status before continuing.
4. Select Tokener.ai and `gemini-embedding-2-preview` again and save. Wait for indexing to finish. Check for documents with `error` status again.

Saving the same provider and model does not start indexing.
Each model change rebuilds completed, enabled, non-archived documents only.
Both switches can incur embedding charges.
Failed documents remain in `error` status without automatic retries.
Resolve document errors after each switch.
Dify Cloud users cannot clear this cache themselves. Contact Dify support before updating an affected knowledge base.
The effect of mixing old and new vectors on retrieval quality has not been measured.
For `gemini-embedding-001`, query and document inputs still use the same request format.
The plugin does not yet preserve the retrieval task type for this model.

Provider, LLM, and embedding validation use authenticated `GET /v1/models`.
Rerank validation sends a small rerank request. Speech validation sends demo audio or a short speech request.
These validation requests can incur charges.

## Model parameters

The generator reads family rules from `scripts/parameter_profiles.json` and capabilities from the catalog.
The SDK filters parameters that the selected model does not declare.
New reasoning models expose no sampling controls unless a profile explicitly permits them.
Unknown families expose the output limit and catalog-declared structured output controls.

GPT-4o-mini and its 2024-07-18 version expose temperature, top-p, presence penalty, and frequency penalty controls.

The existing GPT-5.6 profile retains seed and reasoning effort controls.
The existing DeepSeek V4, GLM-5.2, and Kimi K3 profiles retain their verified sampling controls and seed.
Other GPT-5, GPT-6, and o-series models expose no unverified sampling or reasoning controls.
Claude, Gemini, Grok, Qwen, DeepSeek, GLM, Kimi, and MiniMax family rules expose sampling only for models without reasoning capability.
Catalog metadata does not describe deployment parameter overrides. Recheck the profiles when the upstream contract or deployment policy changes.

Qwen-Long sends document attachments to the provider for native document processing.
Supported formats are TXT, DOCX, PDF, XLSX, EPUB, MOBI, MD, CSV, JSON, BMP, PNG, JPG, JPEG, and GIF.
The plugin downloads Dify document URLs and sends the original bytes as base64 data through the existing chat endpoint.
The complete JSON request must fit within 32 MiB, including base64 encoding, messages, and parameters.
Each request reserves credit for up to 10 million input tokens and the selected output limit.
Low balances can prevent a small document request. Final charges use measured token usage and release unused credit.
Streaming document requests include token usage.

## Sync models

Run the generator from this plugin directory with a complete Tokener catalog snapshot JSON file.
The snapshot must include restricted models available to your users. The public catalog hides restricted models.
An OpenAI `/v1/models` response lacks the context, capability, and price metadata needed for generation.

```bash
export UV_PROJECT_ENVIRONMENT=/tmp/tokener-plugin-venv
uv run --frozen python scripts/sync_catalog.py --input /tmp/tokener-models.json
uv run --frozen python scripts/sync_catalog.py --input /tmp/tokener-models.json --check
```

The snapshot must contain the complete `items` array. Each item supplies `publicModelId`, `category`, `enabled`, `managedAvailable`, and model metadata.
The generator includes models with both `enabled: true` and `managedAvailable: true`, regardless of access scope.
Both display labels use the public model ID. Internal identifiers and display names are excluded.
Decision routes are outside the supported Dify model types. Unknown categories stop generation and identify the affected public model IDs.
Keep the source snapshot outside Git. The snapshot does not prove that a particular API key has model access.

The generator also accepts a complete machine catalog snapshot with `schemaVersion: 1`, `catalogRevision`, and `models`.
The input path is required. If the file contains an HTML login page, re-authenticate and obtain a new JSON snapshot.
Never put keys in snapshots or commits.

The default selection is all five supported types.
Select `--model-type llm`, `text_embedding`, `rerank`, `tts`, or `speech2text` to update one type.
Synchronization validates all selected types before writing. It deletes model YAMLs that lack a matching snapshot entry in each selected type.
An empty type produces an empty position list and removes its model definitions. `--check` reports drift without writing.

Embedding prices use the catalog input price. Rerank and audio definitions omit optional Dify prices because their billing units differ.
Tokener.ai determines charges. Audio models require complete voice or upload metadata and prices.
New audio models use their catalog type and metadata, without an ID allowlist.

## Audio behavior

Speech recognition uploads files to `/v1/audio/transcriptions`. Upload limits and extensions come from catalog metadata. Upload limits use decimal megabytes.
The diarization model uses automatic chunking and returns text without speaker labels.
Text-to-speech sends requests to `/v1/audio/speech`. Voices, languages, the default voice, text limits, and format come from catalog metadata.
Voice languages must use Dify UI locale codes. An unsupported code stops generation and identifies the model, voice, and code.

Long speech text is split into sequential requests. The text limit counts characters, as in the OpenAI plugin.
The plugin streams audio bytes in order. A later failure raises an error after any audio already sent.
An empty stream raises an error. Supported formats are `mp3`, `aac`, `opus`, and `pcm`.
`wav` and `flac` are rejected because concatenated files can truncate playback.

Audio definitions appear only when the snapshot contains matching available models.
Live audio generation, Dify playback, and production latency remain unverified.
A segment without output for more than 120 seconds can exceed the serverless idle limit.

When Tokener returns a JSON error message, document requests show its sanitized
text with the HTTP status. Messages that identify balance or rate-limit failures
remain distinct. Credential values and bearer tokens are redacted. Non-JSON
error pages use a generic HTTP-status message.

## Support

Open an issue in [dify-official-plugins](https://github.com/langgenius/dify-official-plugins/issues).
Include the Dify version, plugin version, model ID, and request ID. Never include API keys or prompt content.

Apache License 2.0. See [LICENSE](https://github.com/langgenius/dify-official-plugins/blob/main/LICENSE).
