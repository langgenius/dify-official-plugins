# Overview

OrcaRouter is an **OpenAI-compatible LLM gateway** that routes requests across 40+ upstream providers (OpenAI, Anthropic, Google, DeepSeek, Qwen, Grok, and more) to the cheapest or fastest path that can serve the model you asked for. Users pay **below list price**, and the dashboard tracks how much they save in real time.

# Configuration

After installation, sign up at [orcarouter.ai](https://www.orcarouter.ai), grab an API key from the [console](https://www.orcarouter.ai/console), and set it up under **Settings → Model Provider** in Dify.

# Adaptive routing — `orcarouter/auto`

The `orcarouter/auto` model is a virtual router that picks the best upstream per request. Configure its strategy from the [routing console](https://www.orcarouter.ai/console/routing). Available strategies:

| Strategy | Behavior |
|---|---|
| `cheapest` | Lowest-priced upstream that can serve the request (default) |
| `balanced` | Trades off price vs latency vs quality |
| `quality` | Highest-quality upstream |
| `adaptive` | Linear contextual bandit picks among candidates based on per-request features (prompt length, code/math/JSON density, declared `max_tokens` budget tier, MinHash-LSH similarity to recent traffic) |
| `gated_adaptive` | Layers a task-difficulty score on top of `adaptive` — mundane prompts restricted to a "weak" model pool, hard prompts to a "strong" pool |

**Why this matters**

- **Self-tuning** — adaptive strategies learn from your own traffic; performance shifts when workload changes
- **Microsecond overhead** — feature extraction and bandit are closed-form math; routing adds no measurable latency
- **Workload-aware in one call** — same `orcarouter/auto` endpoint serves cheap summarization and premium code-refactor requests with no client-side dispatch logic
- **Cost & reliability guardrails by construction** — reward explicitly penalizes cost, latency, rate-limit, and format failures
- **Admin-tunable without redeploys** — strategies, pools, thresholds, and reward weights are changed from console, not client code

# Fallback routing (`extra_body`)

OrcaRouter supports an OpenAI-compatible extension to specify per-request fallback models. Use the **`Fallback models`** and **`Routing mode`** parameters in the model node:

| Parameter | Example | Effect |
|---|---|---|
| `Fallback models` (string, JSON array) | `["openai/gpt-4o-mini", "openai/gpt-4o"]` | If the primary upstream fails, try these in order |
| `Routing mode` | `fallback` | Activate the fallback list above |

These are translated to the request body's `extra_body: {models, route}` key — see the [API reference](https://docs.orcarouter.ai).

# Reasoning models

Some models (OpenAI `o1`/`o3`/`gpt-5`, Anthropic `claude-opus-4.7`, DeepSeek `deepseek-reasoner`/`deepseek-r1`) expose reasoning controls:

- **OpenAI o-style**: `reasoning_effort` (high / medium / low / minimal), `verbosity`, `exclude_reasoning_tokens`
- **Anthropic thinking**: `enable_thinking`, `reasoning_budget` (token budget), `exclude_reasoning_tokens`
- **DeepSeek r-style**: `exclude_reasoning_tokens` (the model reasons by default)

These map onto the upstream provider's native reasoning protocol — OrcaRouter handles the translation.

Reasoning models do not accept `temperature`. The Dify UI will show `temperature` only for non-reasoning models.

# Pricing

All prices are configured at the per-model level in this plugin and reflect the **effective price you pay through OrcaRouter** (which may be below the upstream's list price). See the live [models page](https://www.orcarouter.ai/models) or `GET https://www.orcarouter.ai/api/pricing` for the authoritative source.
