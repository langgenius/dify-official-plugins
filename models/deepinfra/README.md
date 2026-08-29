# DeepInfra

DeepInfra serves open-weight LLMs and embedding models through an OpenAI-compatible
API at a low per-token price, and can be used directly from Dify.

## Features
- Provides `llm` and `text-embedding` models in Dify.
- Ships the full DeepInfra catalog: **106 chat models** and **24 embedding models**,
  so every model DeepInfra advertises is selectable without typing an ID.
- Capability flags are measured, not guessed: `context_size` and pricing come from
  DeepInfra's `/v1/openai/models` metadata, `vision` from its model tags, and
  `tool-call` from probing every chat model against the live API — 10 of the 106 do
  not support tool calling and are marked accordingly.
- Supports predefined model and customizable model configuration. Models DeepInfra
  adds after this release can be used immediately through **customizable model**
  configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get an API key from [DeepInfra](https://deepinfra.com/dash/api_keys).
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Usage
Select **DeepInfra** as the model provider in Dify, choose an available model, and use
it in applications, agents, or workflows.

To use a model released after this plugin version, choose **Add Model**, enter the
DeepInfra model ID exactly as it appears on the
[DeepInfra models page](https://deepinfra.com/models), and set the context size and
capability flags to match that model.

### Reasoning models
Several DeepInfra models emit `reasoning_content` before their answer. With a small
`max_tokens` budget the whole allowance can be spent reasoning, leaving the visible
response empty. Give reasoning models at least ~1000 max tokens.

## Privacy
This plugin sends the inputs required by the selected operation to DeepInfra. Review
[DeepInfra's privacy policy](https://deepinfra.com/privacy) before use.
