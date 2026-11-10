## Overview

GPUStack is an open-source GPU cluster manager for running AI models.

## Key Features
- Broad Hardware Compatibility: Run with different brands of GPUs in Apple Macs, Windows PCs, and Linux servers.
Broad Model Support: From LLMs to diffusion models, audio, embedding, and reranker models.
- Scales with Your GPU Inventory: Easily add more GPUs or nodes to scale up your operations.
- Distributed Inference: Supports both single-node multi-GPU and multi-node inference and serving.
- Multiple Inference Backends: Supports llama-box (llama.cpp & stable-diffusion.cpp), vox-box and vLLM as the inference backends.
- Lightweight Python Package: Minimal dependencies and operational overhead.
- OpenAI-compatible APIs: Serve APIs that are compatible with OpenAI standards.
- User and API key management: Simplified management of users and API keys.
- GPU metrics monitoring: Monitor GPU performance and utilization in real-time.
- Token usage and rate metrics: Track token usage and manage rate limits effectively.

## Quickstart

You need setup your own GPUStack server. Please refer to GPUStack official docs [quickstart](https://docs.gpustack.ai/latest/quickstart/)

## Configure

After setting up your GPUStack server, you will need the following to configure this plugin:

- GPUStack Server URL (e.g., http://yourserveraddress:port)
- GPUStack API Key

Obtain these from your GPUStack server, then enter them into the settings. Click "Save" to activate the plugin.

## Multimodal embedding and reranking

Version 0.0.18 adds opt-in visual capabilities to the embedding and rerank model
types. Register each deployment under its model type and enable **Vision Support**.
Compatibility is determined by the deployed endpoint's request protocol. Model
names select deployments and do not select or inject model-specific templates.
The server URL accepts the GPUStack root URL, `/v1`, or `/v1-openai`. The optional
API endpoint model name selects the upstream deployment when the Dify registration
uses a different name.

With embedding vision enabled, both text and image inputs use the chat-embeddings
protocol at `/v1/embeddings`, as supported by vLLM-compatible endpoints. Each input
is sent as a separate user message conversation and produces one vector in the
original input order. The server applies the deployed model's chat template.
Images from Dify are converted from raw base64 or data URIs into `image_url` content
blocks. Token usage is aggregated from the upstream responses.

By default, the plugin sends a single user message and delegates template flags to
the server. Models with additional requirements can use these optional settings.

- **Embedding system prompt** adds the configured system message to both text and
  image requests when the serving template accepts a system role.
- **Embedding template options (JSON)** accepts boolean `add_generation_prompt`,
  `continue_final_message`, and `add_special_tokens` values. Empty settings use
  server defaults. Enabling continuation appends an empty final assistant message.
  Continuation and generation prompts are mutually exclusive.

The credentials check exercises the configured chat-embedding path with a text
probe. Validate image inference and retrieval with real image inputs as well.

Multimodal reranking sends typed `content` blocks to `/v1/rerank`. Text queries,
image queries, and mixed text/image candidates are supported. Returned indexes
refer to the original candidate list. The endpoint must accept this structured
multimodal rerank protocol and apply the scoring template required by its deployed
model. Configure GPUStack template transformations according to that model's
serving requirements so image content remains structured throughout forwarding.
With vision enabled, the credentials check uses the structured rerank path with
text candidates. Image-query and image-candidate inference require a separate
test with actual images.

Changing embedding preprocessing changes the vectors. Use a new Dify model
registration name mapped to the existing deployment and reindex the knowledge
base, so vectors cached under the previous registration cannot be reused.

Dify 1.17.1 routes text-query multimodal reranking back through its text-only
runner, which filters image candidates. End-to-end text-to-image reranking also
requires updating that Dify runner to pass a typed text query and the retained
image candidates to `invoke_multimodal_rerank`. This plugin implements the model
interface used by that call.

Run the plugin contract tests from this directory after `uv sync --frozen`:

```bash
uv run python -m unittest discover -s tests -v
```
## Configurable LLM timeout (0.0.19)

In Dify's **Add/Edit model** form, LLM models expose **Request read timeout
(seconds)** / **请求读取超时（秒）**. Set a positive number such as `300`, `600`,
or `900`. The value is applied independently for each model, to streaming and
non-streaming inference, credential validation, and validation retries. The
connection timeout remains 10 seconds. This setting is a read inactivity timeout,
not a total generation deadline: a stream that continues receiving data can run
longer. It is not sent as an inference parameter to GPUStack.

If the field is absent or blank, the plugin reads `MAX_REQUEST_TIMEOUT` from its
process environment (SDK default: 300 seconds). The plugin entrypoint also reads
this environment setting instead of fixing it at 120. For Serverless installations,
set that environment value high enough for the desired wait between plugin
messages; the per-model field does not change this separate server-level deadline.
Dify/plugin-daemon and reverse proxy deadlines must also accommodate the request.
