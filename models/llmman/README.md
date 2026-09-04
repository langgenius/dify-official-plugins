## Overview

[llmman](https://github.com/llmmanorg/llmman) is a local model runner that serves the Ollama API (alongside OpenAI- and Anthropic-compatible ones) on port 17434. Models are pulled as OCI artifacts (Docker Hub, GHCR, quay, any registry) or straight from Hugging Face (`hf.co/org/model`) and served by upstream `llama.cpp` (`llama-server`), `vllm`, or `mlx-lm`.

This plugin talks to llmman's OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`) and is a thin preset over the Dify SDK's OpenAI-compatible model classes.

## Capabilities

| Capability | Support | Notes |
| --- | --- | --- |
| Streaming | Yes | Standard OpenAI SSE streaming. |
| Vision | Yes | Enable `Vision support` for multimodal models. |
| Embeddings | Yes | Use model type `Text Embedding`; the plugin calls `/v1/embeddings`. |
| Tool calling | Yes | Enable `Function call support` for tool-capable chat models. |

## Configure llmman Models

#### 1. Install llmman

```bash
curl -fsSL https://raw.githubusercontent.com/llmmanorg/llmman/main/install.sh | sh
```

On Windows: `irm https://raw.githubusercontent.com/llmmanorg/llmman/main/install.ps1 | iex`

#### 2. Start the server and pull a model

```bash
llmman serve
```

In a second terminal:

```bash
llmman pull gemma4
```

The local API is available at `http://localhost:17434`. Override the bind address with `LLMMAN_HOST=[host][:port]`.

#### 3. Add a model in Dify

Go to `Settings > Model Providers > llmman` and add a model.

- Model Name: for example `gemma4`, `qwen3.8`, or `hf.co/unsloth/Qwen3.5-0.8B-GGUF`
- Base URL: `http://localhost:17434/v1` (default). For Docker deployments use a host reachable from the Dify container, such as `http://host.docker.internal:17434/v1`
- API Key: not required by llmman; leave blank
- Model Type: `Chat` for tool calling, vision, and multi-turn chat
- Model context size / Upper bound for max tokens: match the model
