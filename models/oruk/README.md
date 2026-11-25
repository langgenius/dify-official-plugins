# Oruk Speech-to-Text Plugin

English speech recognition for Dify powered by **Oruk Fourier-2B**
(`oruk-fourier-2b`), supporting both Oruk's hosted OpenAI-compatible Speech API
and self-hosted deployments of the open-weights checkpoint
[`oruk/oruk-fourier-2b`](https://huggingface.co/oruk/oruk-fourier-2b).

## Model Overview

- **Predefined model:** `oruk-fourier-2b` (`2.04B` parameters, English-only
  batch speech-to-text)
- **Supported audio formats:** `flac`, `mp3`, `m4a`, `ogg`, `wav`, `webm`
- **Hosted upload limits:** up to `30 MiB` and `60 minutes` per audio file
- **Hosted reference rate:** `$0.0080 / audio minute` (`$0.48 / audio hour`;
  see [Oruk Pricing](https://oruk.ai/pricing) and live
  [`/v1/pricing`](https://speech-api.oruk.ai/v1/pricing))
- **Benchmark context:** On the
  [Hugging Face Open ASR Leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard)
  (`v1.16.3`, evaluated on H200 BF16 with default 3-beam decoding),
  `oruk/oruk-fourier-2b` scored `5.52%` average WER across 9 datasets
  (`#7/68` overall; `4.95%` vs. `5.75%` 7-public-split mean over greedy base
  `Qwen/Qwen3-ASR-1.7B-hf`). Actual accuracy and latency vary by audio
  conditions and deployment hardware.
- **Limitations:** `oruk-fourier-2b` performs English batch transcription only
  (no WebSocket streaming, speaker diarization, or non-English audio).

## Setup

### Option 1: Hosted Oruk Speech API (Default)

1. Create an account and API key at [oruk.ai/auth/signup](https://oruk.ai/auth/signup).
2. In Dify, open **Settings -> Model Provider -> Oruk**.
3. Enter your **API Key** and keep the default **Endpoint URL**
   (`https://speech-api.oruk.ai/v1`).
4. Select `oruk-fourier-2b` as your Speech-to-Text model in any Dify workflow,
   chatflow, or agent app.

See the [Oruk API documentation](https://oruk.ai/docs) and
[OpenAPI specification](https://speech-api.oruk.ai/openapi.json) for request
and response details.

### Option 2: Self-Hosted Open-Weights Server (vLLM)

You can self-host `oruk/oruk-fourier-2b` behind an OpenAI-compatible
`/v1/audio/transcriptions` server using `vLLM >= 0.34.0` and
`transformers >= 5.24.0`:

```bash
hf download oruk/oruk-fourier-2b \
  --revision 8c2a8871f1304aa2f634da4fb95e24438c4945b9

vllm serve oruk/oruk-fourier-2b \
  --revision 8c2a8871f1304aa2f634da4fb95e24438c4945b9 \
  --host 0.0.0.0 --port 8000
```

Then configure the plugin with your server's **Endpoint URL** (for example
`http://your-server:8000` or `http://your-server:8000/v1`). Leave **API Key**
blank if your self-hosted server does not require Bearer authentication.

## Licensing Note

- The open weights of [`oruk/oruk-fourier-2b`](https://huggingface.co/oruk/oruk-fourier-2b)
  are released under **CC-BY-NC-4.0** (non-commercial research/evaluation).
- Commercial deployments can use the hosted Oruk Speech API
  (`https://speech-api.oruk.ai/v1`) or the Apache-2.0-licensed sibling model
  [`oruk/orukqwen-asr-1.7b`](https://huggingface.co/oruk/orukqwen-asr-1.7b) via
  Dify's customizable model configuration.
