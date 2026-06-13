# EmpirioLabs

Frontier AI models through one OpenAI-compatible API.

## Overview

EmpirioLabs gives you access to a curated set of frontier language and embedding models through a single OpenAI-compatible API. You point your existing OpenAI client at `https://api.empiriolabs.ai/v1`, use one EmpirioLabs API key, and call any supported model by its slug. Chat completions, streaming, and embeddings all work the way you already expect.

### Key Features

- **One API, many models**: Frontier chat and embedding models behind a single endpoint and a single key.
- **OpenAI-compatible**: Drop-in compatible with the OpenAI Chat Completions and Embeddings APIs, including streaming.
- **Model catalog**: A public `GET /v1/models` catalog lists every model and its capabilities.
- **Long context**: Several models support very large context windows, up to 1M tokens.
- **Tools and reasoning**: Function calling and step-by-step reasoning are supported on capable models.

### Supported Models

| Model | Type | Context window |
|-------|------|----------------|
| `qwen3-7-plus` | LLM (text, vision, tools) | 1,000,000 |
| `qwen3-7-max` | LLM (text, tools) | 1,000,000 |
| `deepseek-v4-pro` | LLM (text, tools) | 1,000,000 |
| `deepseek-v4-flash` | LLM (text, tools) | 1,000,000 |
| `glm-5-1` | LLM (reasoning, tools) | 202,000 |
| `kimi-k2-7-code` | LLM (agentic coding, vision, tools) | 256,000 |
| `minimax-m3` | LLM (multimodal reasoning, tools) | 524,288 |
| `text-embedding-v4` | Text embedding | 8,192 |

This plugin also supports the customizable-model option, so you can add any other model slug from the EmpirioLabs catalog by name.

## Configuration

### Step 1: Get your API key

1. Sign in at [EmpirioLabs](https://platform.empiriolabs.ai).
2. Open [API Keys](https://platform.empiriolabs.ai/dashboard/api-keys).
3. Create a key and copy it.

### Step 2: Set up in Dify

1. Go to **Settings** then **Model Provider**.
2. Find **EmpirioLabs** in the provider list.
3. Enter your API key.
4. Save the configuration.

### Step 3: Start building

Once configured, select any EmpirioLabs model in your apps, agents, and workflows.

## Documentation and Support

- **Website**: [empiriolabs.ai](https://empiriolabs.ai)
- **Documentation**: [docs.empiriolabs.ai](https://docs.empiriolabs.ai)
- **API base URL**: `https://api.empiriolabs.ai/v1`
- **Model catalog**: `https://api.empiriolabs.ai/v1/models`

## Why EmpirioLabs?

1. **Unified access**: Frontier models behind one endpoint and one key.
2. **Compatibility**: Works with existing OpenAI-compatible clients and SDKs.
3. **Built for agents**: Long context, tool calling, and reasoning where the model supports it.

---

For more information, visit [empiriolabs.ai](https://empiriolabs.ai).
