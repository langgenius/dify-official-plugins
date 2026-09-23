# OpenCode Go

Dify model provider plugin for [OpenCode Go](https://opencode.ai/docs/go/).

OpenCode Go is a $10/month subscription gateway for curated open coding models. This plugin exposes those models as a Dify LLM provider.

## Features

- Predefined models from the OpenCode Go catalog (GLM, Kimi, DeepSeek, MiMo, MiniMax, Qwen, LongCat, Hy, Grok, GPT Luna, Muse Spark)
- Customizable model support with an **API Protocol** selector (`chat` / `anthropic` / `responses`)
- Three upstream protocols in one provider:
  - **Chat Completions** (`{base}/chat/completions` + `Authorization: Bearer`) — default for most models
  - **Anthropic Messages** (`{base}/messages` + `x-api-key`) — models that only expose `/messages` (e.g. `minimax-m2.7`)
  - **OpenAI Responses** (`{base}/responses` + `Authorization: Bearer`) — models that only expose `/responses` (e.g. `grok-4.7`, `grok-4.6`, `gpt-5.6-luna`, `muse-spark-*`)
- Sends OpenCode-required headers on **all three** paths:
  - `User-Agent`: `dify-opencode-go-plugin/0.4.0` (not a generic SDK name)
  - `x-opencode-session`: stable id for routing / prompt-cache affinity
- Upstream quirks handled automatically:
  - `kimi-k2.7-code` — forces `temperature=1` / `top_p=0.95` (gateway only accepts these)
  - `gpt-5.6-luna` — strips `temperature` / `top_p` (upstream rejects them)
  - Transient `502` / `503` / `529` are retried with backoff; empty SSE / raw error JSON surface as Dify `InvokeError` (never silent empty text)
  - SSE is always decoded as UTF-8 (OpenCode often omits charset)
  - Outbound requests honor the process / system proxy (`trust_env`)
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
2. **Model ID** = model id from the [Go docs](https://opencode.ai/docs/go/) (e.g. `kimi-k2.6`).
3. **Display Name** (optional) = label shown in the model list. Defaults to the Model ID.
4. Set **API Protocol** to match the model’s endpoint:
   - `chat` (default) → `/chat/completions`
   - `anthropic` → `/messages` (`minimax-m2.7`, other Messages-only ids)
   - `responses` → `/responses` (`grok-4.7`, `grok-4.6`, `gpt-5.6-luna`, `muse-spark-*`)
5. Configure capability toggles as needed:
   - **Thinking / Agent Thought** (default on) — exposes thinking parameters (`enable_thinking`, `thinking_budget`, `reasoning_effort`)
   - **Vision / Audio / Video / Document** — multimodal file support
   - **Structured output** — exposes `response_format` / `json_schema`
6. Optionally set context size / max tokens / function calling.

## Protocol matrix

| Protocol | Endpoint | Auth | Session | UA |
| --- | --- | --- | --- | --- |
| chat | `{base}/chat/completions` | `Authorization: Bearer` | required | required |
| anthropic | `{base}/messages` | `x-api-key` + `anthropic-version: 2023-06-01` | required | required |
| responses | `{base}/responses` | `Authorization: Bearer` | required | required |

Base URL default: `https://opencode.ai/zen/go/v1`.

### Custom model form (0.4.0)

When adding a custom model you can now set:

| Field | Purpose |
| --- | --- |
| **Model ID** | Upstream model id (required) |
| **Display Name** | Label in the model list (optional; defaults to Model ID) |
| **Thinking / Agent Thought** | Default on. Adds `agent-thought` + thinking parameters |
| **Vision / Audio / Video / Document** | Multimodal file support |
| **Structured output** | Adds `response_format` / `json_schema` |
| **API Protocol** | `chat` / `anthropic` / `responses` |
| Function calling / context / max tokens | As before |

### Custom model form (0.4.0)

When adding a custom model you can now set:

| Field | Purpose |
| --- | --- |
| **Model ID** | Upstream model id (required) |
| **Display Name** | Label in the model list (optional; defaults to Model ID) |
| **Thinking / Agent Thought** | Default on. Adds `agent-thought` + thinking parameters |
| **Vision / Audio / Video / Document** | Multimodal file support |
| **Structured output** | Adds `response_format` / `json_schema` |
| **API Protocol** | `chat` / `anthropic` / `responses` |
| Function calling / context / max tokens | As before |

### Predefined models added in 0.3.0

| Model | Protocol | Notes |
| --- | --- | --- |
| Grok 4.7 (`grok-4.7`) | responses | Same Responses-only path as Grok 4.6. **May require outbound proxy from some regions (e.g. CN).** |
| MiMo-V2.6-Flash (`mimo-v2.6-flash`) | chat | Aligns with MiMo-V2.5 multimodal flags (vision / video / audio) |
| MiMo-V2.6-Pro (`mimo-v2.6-pro`) | chat | Aligns with MiMo-V2.5-Pro |

### Predefined models added in 0.2.0

| Model | Protocol | Notes |
| --- | --- | --- |
| MiniMax M2.7 (`minimax-m2.7`) | anthropic | oa-compat `/chat/completions` returns 500; `/messages` works |
| Grok 4.6 (`grok-4.6`) | responses | Documented Responses-only. **May require outbound proxy from some regions (e.g. CN).** |
| GPT 5.6 Luna (`gpt-5.6-luna`) | responses | Documented Responses-only; **region-restricted** in some territories (often needs proxy). Plugin strips `temperature` / `top_p` for this model. |
| Muse Spark 1.3 Contributor | responses | **Region-limited** (Meta geographic policy); contributor tier may use prompts for training |
| Muse Spark 1.2 Contributor | responses | Same as above |

> **Proxy note:** Responses-line models are frequently blocked or geo-restricted.
> From mainland China, set `HTTP_PROXY` / `HTTPS_PROXY` (or enable system proxy)
> before starting the plugin / Dify runtime so outbound HTTPS can leave the region.
> The plugin honors the process / system proxy environment (`trust_env`).

Qwen and MiniMax M3 remain on Chat Completions (oa-compat) even though OpenCode docs list `/messages` as preferred — oa-compat is verified 200 and avoids regressions. MiniMax M2.7 is the exception (chat 500 → routed to anthropic).

### Predefined models removed in 0.3.0

| Model | Reason |
| --- | --- |
| Union Alpha Free (`union-alpha`) | No longer listed in the OpenCode Go catalog (was a limited-time free trial). Custom models can still target the id if the gateway accepts it. |
| MiniMax M2.5 (`minimax-m2.5`) | No longer in the Go "current model list" / usage tables. Removed from predefined models. |

### Deprecation notices

| Model | Offline at (UTC+8) | Migration |
| --- | --- | --- |
| `mimo-v2.5` | **2026-10-21 10:00** | Switch to `mimo-v2.6-flash` |
| `mimo-v2.5-pro` | **2026-10-21 10:00** | Switch to `mimo-v2.6-pro` |

Both models are marked `deprecated: true`. Please migrate before the offline date.

### Model parameter constraints

| Model | Behavior |
| --- | --- |
| `kimi-k2.7-code` | Gateway only accepts `temperature=1` and `top_p=0.95`; the plugin overrides other values. |
| `gpt-5.6-luna` | Upstream rejects `temperature` and `top_p`; the plugin strips them. |

### Multimodal flags

Feature flags (vision / video / document / audio) follow the **official** model capabilities, because OpenCode Go proxies those upstream APIs. Not every modality is re-tested on the gateway for every model.

Local smoke matrix (2026-09-17, 0.2.0 + live-debug fixes). Vision for all vision-flagged models was verified in a Dify workflow by the user:

| Model | Status |
| --- | --- |
| glm-5.3-flash / glm-5.x | OK (stream + non-stream) |
| glm-5.1 / glm-5.2 | OK |
| mimo-v2.6-flash / mimo-v2.6-pro | Not smoke-tested yet (added in 0.3.0) |
| mimo-v2.5 / mimo-v2.5-pro | OK |
| kimi-k2.6 / kimi-k2.7-code / kimi-k3 | OK |
| qwen3.6-plus / qwen3.7-plus / qwen3.7-max / qwen3.8-flash / qwen3.8-max | OK |
| minimax-m3 | OK (chat) |
| minimax-m2.7 | OK (anthropic `/messages`) |
| deepseek-v4-pro / v4-flash / v4.1-flash / flash-vision-exp | OK |
| longcat-2.0 / hy3 / hy4-preview | OK |
| grok-4.7 via responses `/responses` | Not smoke-tested yet (added in 0.3.0) |
| grok-4.6 via responses `/responses` | OK with outbound proxy |
| gpt-5.6-luna via responses | OK with outbound proxy |
| muse-spark-1.3 via responses | HTTP 200 (content quality may vary; region-limited) |

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
python test_custom_model_features.py
```

Live smoke (needs `OPENCODE_GO_API_KEY`):

```bash
python test_smoke_live.py
```

Package:

```bash
dify plugin package models/opencode-go -o dist/opencode_go-0.4.0.difypkg
```

## Links

- OpenCode Go docs: https://opencode.ai/docs/go/
- Models list API: `https://opencode.ai/zen/go/v1/models`
- Auth / API keys: https://opencode.ai/auth
- Dify plugin docs: https://docs.dify.ai/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## Disclaimer

This is an unofficial community plugin. It is not affiliated with OpenCode / Anomaly or Dify.
