# LiteLLM

## Overview

Use a [LiteLLM Proxy](https://docs.litellm.ai/docs/proxy/quick_start) as the model provider for Dify. The proxy gives one OpenAI-compatible endpoint for 100+ model providers, with virtual keys, spend tracking, budgets, and fallbacks.

The plugin adds your proxy models to Dify as customizable models. It supports:

- LLM (chat and completion), including streaming and tool calls
- Text embedding

This plugin is for the LiteLLM Proxy server. It does not use the LiteLLM Python library.

## Configure

1. Start a LiteLLM Proxy. See the [quick start](https://docs.litellm.ai/docs/proxy/quick_start). The default address is `http://localhost:4000`.
2. Optional: create a [virtual key](https://docs.litellm.ai/docs/proxy/virtual_keys) for Dify.
3. Install **LiteLLM** from the Dify Marketplace.
4. Open **Settings → Model Provider → LiteLLM** and select **Add Model**.
5. Choose the model type and enter these values:
   - **Model Name**: the `model_name` alias from your proxy config, for example `gpt-6-luna` for an LLM or `text-embedding-3-large` for an embedding model.
   - **LiteLLM Proxy URL**: for example `http://localhost:4000`. A trailing `/v1` is optional.
   - **API Key**: a virtual key or the master key. Leave it empty if the proxy has no authentication.

Example proxy config:

```yaml
model_list:
  - model_name: gpt-6-luna
    litellm_params:
      model: openai/gpt-6-luna
      api_key: os.environ/OPENAI_API_KEY
  - model_name: text-embedding-3-large
    litellm_params:
      model: openai/text-embedding-3-large
      api_key: os.environ/OPENAI_API_KEY
```

The model names come from your own proxy config. The plugin does not include a model list. For more about the proxy, see [LiteLLM Proxy as a provider](https://docs.litellm.ai/docs/providers/litellm_proxy).

If Dify runs in Docker, `localhost` points to the Dify container. Use `http://host.docker.internal:4000` or the address of the proxy host.

## Usage

- Set **Function Call Type** to **Tool Call** for models that support tools. Agent nodes and tool calling need this setting.
- Set **Vision Support** for models that accept images.
- Set **Model context size** and **Upper bound for max tokens** to the limits of the model.
- For embedding models, set **Model max chunks per batch** to the batch size that the model accepts.

Credential validation sends a small request (`ping`) to `/chat/completions` or `/embeddings`. The model must exist in the proxy config for the check to pass.

When a model answers with tool calls only, the proxy can leave out `message.content`. The plugin treats it as an empty string.

## Support

Open an issue in [dify-official-plugins](https://github.com/langgenius/dify-official-plugins/issues) and include the Dify version, the plugin version, and the model alias. Never include API keys or prompt content.

## License

Apache License 2.0. See the repository [LICENSE](https://github.com/langgenius/dify-official-plugins/blob/main/LICENSE).
