# IO Intelligence Model Provider Plugin

## Overview

This plugin integrates [IO Intelligence](https://io.net/intelligence) as a model provider for Dify. IO Intelligence by io.net provides access to 25+ open-source AI models powered by a decentralized GPU network of 320,000+ GPUs with low-latency inference.

## Configuration

1. Sign up at [IO Intelligence](https://io.net/intelligence)
2. Generate an API key from your dashboard
3. In Dify, add IO Intelligence as a model provider and enter your API key

## Supported Models

| Model | Context Window | Vision | Pricing (Input/Output per 1M tokens) |
|-------|---------------|--------|---------------------------------------|
| DeepSeek V3.2 | 128K | No | $0.25 / $0.38 |
| DeepSeek R1 0528 | 128K | No | $0.40 / $1.75 |
| Llama 4 Maverick 17B 128E | 430K | Yes | $0.15 / $0.60 |
| Llama 3.3 70B Instruct | 128K | No | $0.10 / $0.32 |
| Llama 3.2 90B Vision | 16K | Yes | $0.35 / $0.40 |
| Kimi K2 Thinking | 262K | No | $0.32 / $0.48 |
| Kimi K2 Instruct 0905 | 262K | No | $0.39 / $1.90 |
| Qwen3 Next 80B A3B | 262K | No | $0.06 / $0.60 |
| Qwen2.5 VL 32B | 32K | Yes | $0.05 / $0.22 |
| Qwen3 Coder 480B A35B | 106K | No | $0.22 / $0.95 |
| GLM 5 | 202K | No | $0.94 / $3.00 |
| GLM 4.7 | 202K | No | $0.30 / $1.40 |
| GLM 4.7 Flash | 200K | No | $0.07 / $0.40 |
| GLM 4.6 | 200K | No | $0.35 / $1.50 |
| Mistral Large Instruct 2411 | 128K | Yes | $2.00 / $6.00 |
| Mistral Nemo Instruct 2407 | 128K | No | $0.02 / $0.04 |
| GPT-OSS 120B | 131K | No | $0.02 / $0.10 |
| GPT-OSS 20B | 64K | No | $0.016 / $0.06 |

## API Documentation

IO Intelligence provides an OpenAI-compatible API. For more information, visit [IO Intelligence](https://io.net/intelligence).
