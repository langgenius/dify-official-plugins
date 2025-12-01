## Overview

GMI Cloud is a cloud-based GPU infrastructure platform that provides high-performance AI model inference services. With an OpenAI-compatible API, GMI Cloud delivers fast and reliable access to popular large language models including DeepSeek, Llama, Qwen, and Zhipu models.

## Key Features

- **OpenAI-Compatible API**: Seamless integration with standard OpenAI client libraries and tools.
- **Multiple Model Families**: Access to DeepSeek, Meta Llama, Qwen, OpenAI OSS, and Zhipu (ZAI) models.
- **High Performance**: Optimized GPU infrastructure for fast inference and low latency.
- **Streaming Support**: Real-time streaming responses for chat completions.
- **Tool Calling**: Built-in support for function calling and tool use.
- **Custom Model Support**: Deploy and use your own fine-tuned models.
- **Flexible Endpoints**: Support for custom API endpoints for enterprise deployments.

## Configure

After installing the plugin, you will need the following to configure GMI Cloud:

1. **Get your API Key**: Sign in to the [GMI Cloud console](https://console.gmicloud.ai/user-setting/organization/api-key-management) and create an API key.
2. **Configure in Dify**: Open **Settings → Model Provider**, find **GMI Cloud**, and enter your API key in the `API Key` field.
3. **Custom Endpoint (Optional)**: If your organization uses a custom endpoint, fill in the `API Endpoint URL` field. Otherwise, the plugin defaults to `https://api.gmi-serving.com/v1`.
4. **Save**: Click "Save" to activate the plugin. Dify will validate your credentials by calling the `/v1/models` endpoint.

## Built-in Models

The plugin ships with the following preset models you can use immediately:

- **DeepSeek**: `deepseek-ai/DeepSeek-V3-0324`, `deepseek-ai/DeepSeek-V3.1`
- **OpenAI OSS**: `openai/gpt-oss-120b`
- **Meta Llama**: `meta-llama/Llama-4-Scout-17B-16E-Instruct`
- **Qwen**: `Qwen/Qwen3-32B-FP8`, `Qwen/Qwen3-Next-80B-A3B-Instruct`, `Qwen/Qwen3-235B-A22B-Thinking-2507-FP8`, `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8`
- **Zhipu (ZAI)**: `zai-org/GLM-4.6`