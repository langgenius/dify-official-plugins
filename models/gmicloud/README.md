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

- **DeepSeek**: `DeepSeek V3 0324`, `DeepSeek V3.1`
- **OpenAI OSS**: `OpenAI GPT OSS 120b`
- **Meta Llama**: `llama4-scout-17b-16e-instruct`
- **Qwen**: `qwen3-32b-fp8`, `qwen3-next-80b-a3b-instruct`, `qwen3-next-80b-a3b-thinking`, `qwen3-235b-a22b-instruct-2507-fp8`, `qwen3-235b-a22b-thinking-2507-fp8`, `qwen3-coder-480b-a35b-instruct-fp8`
- **Zhipu (ZAI)**: `zai-glm45-fp8`, `zai-glm45-air-fp8`