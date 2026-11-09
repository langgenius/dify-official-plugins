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

## System-only chat workflows

Some chat templates require a User query even when the full task is supplied in
System messages. For a chat request containing only System messages with real
text, the plugin preserves the instructions and appends the neutral User turn
`Please respond according to the instructions above.`.

The compatibility step checks the original task before adding JSON Schema
instructions. Invocation uses copied prompt messages so retries can reuse the
caller's inputs without accumulating generated instructions. This compatibility
step applies only to nonempty System-only chat requests. Preflight token
estimation includes the same execution turn.
