# FunASR Speech Recognition Plugin

Open-source speech recognition from Alibaba DAMO Academy. 170x faster than Whisper.

## Setup

1. Deploy FunASR server:
```bash
pip install funasr vllm fastapi uvicorn
funasr-server --device cuda --host 0.0.0.0 --port 8000
```

2. In Dify, configure this plugin with your FunASR server URL (e.g. `http://your-server:8000`).

## Supported Models

- **sensevoice** — 50+ languages, emotion detection (default)
- **paraformer** — Chinese, with punctuation
- **paraformer-en** — English
- **fun-asr-nano** — Encoder+LLM architecture
