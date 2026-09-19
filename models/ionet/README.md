# IO Intelligence

Dify model provider plugin for [IO Intelligence](https://io.net) (by io.net).

IO Intelligence serves an OpenAI-compatible **Chat Completions** API at
`https://api.intelligence.io.solutions/api/v1` (Bearer auth; `GET /models` is public).
Model IDs are `org/name` style, e.g. `meta-llama/Llama-3.3-70B-Instruct`.

## Features

- All 35 predefined models from the IO Intelligence catalog (GLM, DeepSeek, Kimi, Qwen, Llama, MiniMax, MiMo, Gemma, Mistral, gpt-oss), with context windows, tool/reasoning/vision/video capabilities, and per-model pricing from the public `/models` endpoint
- Customizable model support for newly added model IDs
- Default base URL: `https://api.intelligence.io.solutions/api/v1`

## Setup

1. Create an API key in the io.net cloud console: https://cloud.io.net
2. Install this plugin in Dify (Marketplace / plugin package / debug remote).
3. Open **Settings → Model Providers → IO Intelligence**, paste the API key, save.
4. Select an IO Intelligence model in your app.

### Custom model

If io.net adds a new model before this plugin is updated:

1. Add a custom model under IO Intelligence.
2. Model name = model ID from the [public catalog](https://api.intelligence.io.solutions/api/v1/models) (e.g. `zai-org/GLM-5.3-Flash`).
3. Optionally set context size / max tokens / function calling / vision.
