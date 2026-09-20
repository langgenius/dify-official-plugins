# Stepfun

Official StepFun model provider plugin for Dify.

## Features
- Provides llm models in Dify.
- Adds predefined support for `step-5-preview` and `step-3.7-flash`.
- Supports tool calling, reasoning controls, structured output, and multimodal input for Step 5 Preview and Step 3.7 Flash.
- Supports predefined model and customizable model configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get the required credentials from [Stepfun](https://platform.stepfun.com/interface-key).
   - **Note:** StepFun operates two separate platforms:
     - **Standard platform** at [platform.stepfun.com](https://platform.stepfun.com) (uses `api.stepfun.com` endpoint - default)
     - **International platform** at [platform.stepfun.ai](https://platform.stepfun.ai) (uses `api.stepfun.ai` endpoint)
   - These are separate account systems. An API key from one platform will not work with the other endpoint.
3. Add the credentials in the plugin settings.
   - If your API key is from the international platform (platform.stepfun.ai), enable the **Use International Endpoint** option.
4. Save the configuration.

`Enable request metadata` is optional and disabled by default. Turning it on attaches `X-Dify-App-Id` and `X-Dify-Source` to each StepFun request as custom HTTP headers, so usage can be attributed to a specific Dify app. The opt-in is routed through the `extra_headers` credential because the SDK's OAICompat base class does not forward body-level metadata to the upstream request. The Dify session lookup is best-effort: if the session context is not initialized, no headers are attached and the request is sent unchanged.

## Usage
Select **Stepfun** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.

## Step 5 Preview

Supports a 1M-token context window and up to 1M output tokens (input and output share the context budget), text/image/video input, tool calling, JSON output, and low/medium/high reasoning effort. Reasoning is displayed in both streaming and non-streaming responses.

The listed price is the standard platform's uncached rate: RMB 7 per million input tokens and RMB 20 per million output tokens. Cached input and international pricing may differ.

Sources: [model specifications](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview), [Chat Completions API](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create), and [pricing](https://platform.stepfun.com/docs/zh/guides/pricing/details).

## StepAudio 3 speech

Enable speech features in your Dify application settings and select **Stepfun**:

- **Text to speech:** select `stepaudio-3-tts` and an official voice. Returns MP3 audio, with long input split into requests of at most 1,000 characters using the same sentence-splitting approach as the OpenAI TTS provider. Parenthesized instructions such as `(高兴地)` can control delivery; StepAudio 3 treats text inside `()` as instructions rather than spoken content.
- **Speech to text:** select `stepaudio-3-asr-max`. Upload WAV, MP3, OGG, or M4A audio, up to this plugin's 25 MiB limit. The plugin calls StepFun's dedicated `/audio/asr/sse` API and returns the final transcript. Partial results are not returned as successful transcriptions when the stream fails or ends early. Raw PCM is not exposed because Dify's file input does not supply its required sample rate, bit depth, and channel count.

Both speech models use the existing API key, international-endpoint selection, and optional Dify metadata headers. Account access and model availability depend on the selected StepFun platform. Provider credential validation continues to use the existing LLM check; individual speech-model validation performs an actual synthesis or transcription request and can incur charges.

TTS uses HTTP audio streaming (`/audio/speech`, `stream_format=audio`), not a bidirectional WebSocket session. The voice picker uses StepFun's official voice catalog; cloned voices and the separate voice-cloning API are not exposed. The standard-platform TTS price is RMB 2.5 per 10,000 characters. ASR is billed upstream at RMB 2.8 per hour; Dify's speech-to-text model schema does not expose duration-based pricing here.

StepAudio 3 Realtime, Music, and Gen have separate session or generation APIs. They are not registered as TTS or speech-to-text models: Dify's native interfaces accept text for speech synthesis or an uploaded audio file for transcription, not bidirectional sessions or music/sound-effect generation requests.

References: [StepAudio 3](https://static.stepfun.com/blog/stepaudio3/), [TTS model](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-tts), [speech synthesis API](https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio), [official voices](https://platform.stepfun.com/docs/zh/guides/developer/tts), [ASR model](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-asr), and [ASR SSE API](https://platform.stepfun.com/docs/zh/api-reference/audio/asr-sse).
