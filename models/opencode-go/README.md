# OpenCode Go

Dify model provider plugin for [OpenCode Go](https://opencode.ai/docs/go/).

OpenCode Go is a $10/month subscription gateway for curated open coding models. This plugin exposes those models as a Dify LLM provider.

## Features

- Predefined models from the OpenCode Go catalog (GLM, Kimi, DeepSeek, MiMo, MiniMax, Qwen, LongCat, Hy, Grok, GPT Luna, Muse Spark, Union Alpha)
- Customizable model support with an **API Protocol** selector (`chat` / `anthropic` / `responses`)
- Three upstream protocols in one provider:
  - **Chat Completions** (`{base}/chat/completions` + `Authorization: Bearer`) — default for most models
  - **Anthropic Messages** (`{base}/messages` + `x-api-key`) — models that only expose `/messages` (e.g. `union-alpha`)
  - **OpenAI Responses** (`{base}/responses` + `Authorization: Bearer`) — models that only expose `/responses` (e.g. `grok-4.6`, `gpt-5.6-luna`, `muse-spark-*`)
- Sends OpenCode-required headers on **all three** paths:
  - `User-Agent`: `dify-opencode-go-plugin/0.2.0` (not a generic SDK name)
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
- The internal helper header `x-dify-run-id` is never forwarded upstream.

## Setup

1. Subscribe to OpenCode Go at [opencode.ai/auth](https://opencode.ai/auth) and copy your API key.
2. Install this plugin in Dify (Marketplace / plugin package / debug remote).
3. Open **Settings → Model Providers → OpenCode Go**, paste the API key, save.
4. Select an OpenCode Go model in your app.

### Custom model

If OpenCode adds a new model before this plugin is updated:

1. Add a custom model under OpenCode Go.
2. Model name = model id from the [Go docs](https://opencode.ai/docs/go/) (e.g. `kimi-k2.6`).
3. Set **API Protocol** to match the model’s endpoint:
   - `chat` (default) → `/chat/completions`
   - `anthropic` → `/messages` (`union-alpha` and other Messages-only ids)
   - `responses` → `/responses` (`grok-4.6`, `gpt-5.6-luna`, `muse-spark-*`)
4. Optionally set context size / max tokens / function calling / vision.

## Protocol matrix

| Protocol | Endpoint | Auth | Session | UA |
| --- | --- | --- | --- | --- |
| chat | `{base}/chat/completions` | `Authorization: Bearer` | required | required |
| anthropic | `{base}/messages` | `x-api-key` + `anthropic-version: 2023-06-01` | required | required |
| responses | `{base}/responses` | `Authorization: Bearer` | required | required |

Base URL default: `https://opencode.ai/zen/go/v1`.

### Predefined models added in 0.2.0

| Model | Protocol | Notes |
| --- | --- | --- |
| Union Alpha Free (`union-alpha`) | anthropic | Free / limited time; oa-compat `/chat/completions` returns 500 |
| Grok 4.6 (`grok-4.6`) | responses | Documented Responses-only |
| GPT 5.6 Luna (`gpt-5.6-luna`) | responses | Documented Responses-only; **region-restricted** in some territories |
| Muse Spark 1.3 Contributor | responses | **Region-limited** (Meta geographic policy); contributor tier may use prompts for training |
| Muse Spark 1.2 Contributor | responses | Same as above |

Qwen / MiniMax remain on Chat Completions (oa-compat) even though OpenCode docs list `/messages` as the preferred endpoint — oa-compat is verified 200 and avoids regressions.

Local smoke test against a real OpenCode Go key (2026-09-16, 0.2.0):

| Model | Status |
| --- | --- |
| glm-5.3-flash / glm-5.x | OK (stream + non-stream) |
| mimo-v2.5 | OK |
| kimi-k2.6 | OK |
| qwen3.8-flash | OK |
| minimax-m3 | OK |
| union-alpha via anthropic `/messages` | OK (stream + non-stream) |
| union-alpha via chat `/chat/completions` | 500 (expected) |
| grok-4.6 via responses `/responses` | OK (stream + non-stream) |
| gpt-5.6-luna via responses | **Region blocked** from some hosts (`unsupported_country_region_territory`) |
| muse-spark-* | Region restricted (not always callable) |

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
python test_protocol_routing.py
```

Live smoke (needs `OPENCODE_GO_API_KEY`):

```bash
python test_smoke_live.py
```

Package:

```bash
dify plugin package models/opencode-go -o dist/opencode_go-0.2.0.difypkg
```

## Links

- OpenCode Go docs: https://opencode.ai/docs/go/
- Models list API: `https://opencode.ai/zen/go/v1/models`
- Auth / API keys: https://opencode.ai/auth
- Dify plugin docs: https://docs.dify.ai/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## Disclaimer

This is an unofficial community plugin. It is not affiliated with OpenCode / Anomaly or Dify.
