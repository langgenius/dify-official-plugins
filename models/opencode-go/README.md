# OpenCode Go

Dify model provider plugin for [OpenCode Go](https://opencode.ai/docs/go/).

OpenCode Go is a $10/month subscription gateway for curated open coding models. This plugin exposes those models as a Dify LLM provider over the OpenAI-compatible Chat Completions API.

## Features

- Predefined models from the OpenCode Go catalog (GLM, Kimi, DeepSeek, MiMo, MiniMax, Qwen, LongCat, Hy)
- Customizable model support for newly added model IDs
- Sends OpenCode-required headers:
  - `User-Agent`: `dify-opencode-go-plugin/0.1.0` (not a generic SDK name)
  - `x-opencode-session`: stable id for routing / prompt-cache affinity
- Session isolation (recommended): enable the LLM-node model parameter `extra_headers` and keep the default JSON. Dify resolves `{{#sys.*#}}` before invoke; the plugin then picks:
  - Chatflow / chat apps: conversation id → one session per conversation
  - Workflow apps: `workflow_run_id` (via the internal helper header) → one session per run, shared by LLM nodes in that run

```json
{
  "x-opencode-session": "{{#sys.conversation_id#}}",
  "x-dify-run-id": "{{#sys.workflow_run_id#}}"
}
```

- Fallbacks when `extra_headers` is absent or leaves session empty:
  1. Provider credential `session_id` (optional static override)
  2. Plugin Session `conversation_id` when Dify provides it
  3. Per-invoke isolation (RPC session id or a random UUID) — never sticky on Dify user id
- Unresolved Dify templates (`{{#sys.*#}}`) are never sent as session values.

## Setup

1. Subscribe to OpenCode Go at [opencode.ai/auth](https://opencode.ai/auth) and copy your API key.
2. Install this plugin in Dify (Marketplace / plugin package / debug remote).
3. Open **Settings → Model Providers → OpenCode Go**, paste the API key, save.
4. Select an OpenCode Go model in your app.

### Custom model

If OpenCode adds a new model before this plugin is updated:

1. Add a custom model under OpenCode Go.
2. Model name = model id from the [Go docs](https://opencode.ai/docs/go/) (e.g. `kimi-k2.6`).
3. Optionally set context size / max tokens / function calling / vision.

## Protocol notes

This plugin uses the OpenAI-compatible path (`{base}/chat/completions`).

Local smoke test against a real OpenCode Go key (2026-09-10):

| Model | Status |
| --- | --- |
| glm-5.3-flash / glm-5.x | OK (stream + non-stream) |
| mimo-v2.5 | OK |
| kimi-k2.6 | OK |
| deepseek-v4-flash | OK |
| qwen3.8-flash / qwen3.7-plus | OK |
| hy3 | OK |
| minimax-m3 | OK |
| minimax-m2.7 | Gateway 500 (may be temporary) |
| grok-4.6 / gpt-5.6-luna | Not supported via `oa-compat` (Responses API only) |
| muse-spark-* | Region restricted / Responses only |

Grok / GPT 5.6 Luna / Muse Spark are **not** included as predefined models because OpenCode Go rejects them on the Chat Completions endpoint (`Model ... is not supported for format oa-compat`).

## Development / debug

```bash
pip install "dify_plugin>=0.10.0"
```

Copy `.env.example` to `.env` and set your Dify debug key from **Plugins → debug**.

```bash
python -m main
```

Local unit tests (no network):

```bash
python test_session_id.py
python test_session_runtime.py
python test_extra_headers.py
python test_backward_compat_002.py
```

Package:

```bash
dify plugin package models/opencode-go -o dist/opencode_go-0.1.0.difypkg
```

## Links

- OpenCode Go docs: https://opencode.ai/docs/go/
- Models list API: `https://opencode.ai/zen/go/v1/models`
- Auth / API keys: https://opencode.ai/auth
- Dify plugin docs: https://docs.dify.ai/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## Disclaimer

This is an unofficial community plugin. It is not affiliated with OpenCode / Anomaly or Dify.
