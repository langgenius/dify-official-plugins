# FunASR Speech Recognition Plugin

Self-hosted speech recognition through FunASR's OpenAI-compatible API. The
plugin supports multilingual ASR models for private Dify deployments without
sending audio to a hosted transcription service.

In FunASR's
[192-minute benchmark](https://modelscope.github.io/FunASR/benchmark.html),
SenseVoiceSmall reached 170x real-time on GPU and 17x real-time on CPU.
Whisper-large-v3 reached 13x real-time on GPU in the same benchmark. Results
depend on the hardware, audio, model, and concurrency settings.

## Setup

1. Deploy a SenseVoice server:

```bash
pip install "funasr>=1.3.26" fastapi uvicorn python-multipart
funasr-server --device cuda --model sensevoice --host 0.0.0.0 --port 8000
```

Use `--device cpu` when CUDA is unavailable. Fun-ASR-Nano deployments use
vLLM and can be installed separately:

```bash
pip install "funasr>=1.3.26" vllm fastapi uvicorn python-multipart
funasr-server --device cuda --model fun-asr-nano --host 0.0.0.0 --port 8000
```

2. In Dify, configure this plugin with the server URL, for example
   `http://your-server:8000` or `http://your-server:8000/v1`. The plugin
   normalizes both forms to a base URL ending in `/v1`, such as
   `http://localhost:8000/v1`. Leave the API key empty when the server does
   not require one.

Predefined models accept audio files up to 25 MB.

## Supported Models

- **sensevoice** - Mandarin, Cantonese, English, Japanese, and Korean ASR with
  emotion and audio-event tags (default)
- **paraformer** - Chinese ASR with punctuation
- **paraformer-en** - English ASR
- **fun-asr-nano** - Chinese, English, Japanese, and Chinese dialect/accent ASR
  with an encoder + LLM architecture
