# DeepInfra

DeepInfra serves open-weight LLMs and embedding models through an OpenAI-compatible
API at a low per-token price, and can be used directly from Dify.

## Features
- Provides `llm` and `text-embedding` models in Dify.
- Includes 26 predefined LLMs such as `openai/gpt-oss-120b`, `deepseek-ai/DeepSeek-V4-Flash-0731`,
  `meta-llama/Llama-3.3-70B-Instruct-Turbo`, `Qwen/Qwen3-235B-A22B-Instruct-2507` and
  `zai-org/GLM-5.3-Flash`, including vision-capable models.
- Includes 8 predefined embedding models such as `BAAI/bge-m3`, `Qwen/Qwen3-Embedding-8B`
  and `intfloat/multilingual-e5-large`.
- Supports predefined model and customizable model configuration. DeepInfra hosts far
  more models than are predefined here — any other model ID can be added through
  **customizable model** configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get an API key from [DeepInfra](https://deepinfra.com/dash/api_keys).
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Usage
Select **DeepInfra** as the model provider in Dify, choose an available model, and use
it in applications, agents, or workflows.

To use a model that is not predefined, choose **Add Model**, enter the DeepInfra model
ID exactly as it appears on the [DeepInfra models page](https://deepinfra.com/models)
(for example `Qwen/Qwen3-Next-80B-A3B-Instruct`), and set the context size and
capability flags to match that model.

## Privacy
This plugin sends the inputs required by the selected operation to DeepInfra. Review
[DeepInfra's privacy policy](https://deepinfra.com/privacy) before use.
