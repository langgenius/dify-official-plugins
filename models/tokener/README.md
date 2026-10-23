# Tokener.ai

## Overview

Tokener.ai model provider for Dify. The plugin calls chat completions, rerank, text embeddings, speech recognition, and text-to-speech through a fixed Tokener.ai endpoint.

## Configure

1. Install **Tokener.ai** from the Dify Marketplace.
2. Create an API key in the [Tokener.ai Console](https://console.tokener.dev/keys).
3. Open **Settings → Model Provider → Tokener.ai** and enter the key.

The API endpoint is fixed to `https://api.tokener.dev/v1`. The plugin does not accept provider keys, LiteLLM keys, organization IDs, or custom endpoints.

## Usage

In a Dify Workflow or Chatflow, add an LLM node, select **Tokener.ai**, and choose an available model.

Provider, LLM, and embedding validation use authenticated `GET /v1/models`. Rerank model validation sends one small rerank request to check model access. Speech recognition validation sends the SDK demo audio to the selected model. Text-to-speech validation sends a short speech request with the default voice.

Select **Qwen3 Rerank** as a rerank model. The API key must have access to `qwen3-rerank`. The public model directory does not list restricted rerank models.

The plugin registers a text embedding adapter. No predefined embedding models are included because the verified catalog lists none. The adapter needs matching model definitions before embedding models appear in Dify. Embeddings keep the requested model ID and the default vector dimensions. The plugin does not truncate texts or switch models.

## Speech recognition

Select Tokener.ai in Dify speech-to-text configuration. The predefined models are `whisper-1`, `gpt-4o-mini-transcribe`, `gpt-4o-mini-transcribe-2025-12-15`, `gpt-4o-transcribe`, and `gpt-4o-transcribe-diarize`.

Requests upload the file to `/v1/audio/transcriptions` with the selected model ID. The diarization model uses automatic chunking and returns the response text without speaker labels. Upload limits and file extensions come from the catalog audio metadata. The adapter closes the upload file on success and failure.

The audio route is not yet available for live verification. Tests use mock HTTP responses and contract fixtures.

## Text-to-speech

Select Tokener.ai in Dify text-to-speech configuration. The predefined models are `tts-1` and `tts-1-hd`.

The plugin sends JSON requests to `/v1/audio/speech` with the selected model ID. Voices, language codes, the default voice, the text limit, and the audio format come from catalog metadata. Empty or invalid voices use the catalog default. Language filtering matches catalog language codes exactly.

Long text follows the OpenAI plugin sentence splitter and is then split to each model's `wordLimit`. As in the reference plugin, this limit counts characters. Requests run in sequence, and the plugin streams their audio bytes in order. If a later request fails, the stream raises an error after any audio already sent. All-empty audio responses raise an error.

The plugin accepts `mp3`, `aac`, `opus`, and `pcm` and sends the catalog format unchanged. Catalog sync and invocation reject `wav` and `flac` because combining separate files can truncate playback.

The speech route is not yet available for live verification. Tests use mock HTTP. Dify playback of the configured format remains unverified. A segment with no audio output for more than 120 seconds can exceed the serverless idle limit. Real upstream latency still needs measurement.

## Model parameters

Parameter rules come from the catalog generator and explicit model profiles. The SDK does not send parameters that the selected model does not declare. New model IDs receive no sampling or reasoning controls until their API contract is verified.

| Models | Temperature | Top P | Presence penalty | Frequency penalty | Seed | Reasoning effort | Thinking |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna | Not declared | Not declared | Not declared | Not declared | Integer | none, low, medium, high, xhigh | Not declared |
| deepseek-v4-flash, deepseek-v4-pro, glm-5.2, kimi-k3 | 0–2 | 0.01–1 | -2–2 | -2–2 | Integer | Not declared | Not declared |

Staging GPT requests return HTTP 400 for custom temperature and Top P, even with `reasoning_effort=none`. GPT models do not expose these controls. Dify built-in calls can still supply them. The SDK filters these undeclared parameters before HTTP and sends declared parameters. DeepSeek and GLM deployment policies remove thinking controls, so the plugin does not declare them. Kimi reasoning effort is not declared because its effect is unverified. Seed forwarding does not guarantee repeatable output.

Profiles use the API parameter policy and the LiteLLM 1.103.0-rc.1 contract. Staging requests confirm request acceptance for the tested models and values. They do not prove parameter effects or production deployment settings. Production parameter overrides and DeepSeek Flash inference remain unverified. Recheck these profiles when deployment policies change. Catalog revisions do not include parameter policies.

## Sync models

Model YAML is generated from the Tokener.ai public catalog:

```bash
uv run python scripts/sync_catalog.py
uv run python scripts/sync_catalog.py --check
```

The default command generates only LLM entries. To generate speech recognition or text-to-speech definitions, select `--model-type speech2text` or `--model-type tts`.

The public catalog does not yet contain audio models. The included audio definitions use the contract fixture, not live catalog results:

```bash
uv run python scripts/sync_catalog.py --model-type speech2text --url "file://$PWD/tests/fixtures/speech2text_catalog.json"
uv run python scripts/sync_catalog.py --model-type tts --url "file://$PWD/tests/fixtures/tts_catalog.json"
```

Add `--check` to compare the generated files. Each command writes only the selected model type. Sync stops without writing if the catalog contains no supported models for the selected type. Fixture prices are synthetic. The SDK cannot express all audio billing dimensions, so audio definitions omit the optional Dify price display. Tokener.ai determines charges.

## Support

Open an issue in [dify-official-plugins](https://github.com/langgenius/dify-official-plugins/issues) and include the Dify version, plugin version, model ID, and request ID. Never include API keys or prompt content.

## License

Apache License 2.0. See the repository [LICENSE](https://github.com/langgenius/dify-official-plugins/blob/main/LICENSE).
