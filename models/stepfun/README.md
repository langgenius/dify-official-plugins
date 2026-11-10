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

### Official voice catalog (0.2.1)

The voice picker reads the following 36 voices from the bundled model schema; listing them requires no API call. English (`en-US`, `en_US`, `en`) and Chinese (`zh-Hans`, `zh_Hans`, `zh-CN`, `zh_CN`, `zh`) locale spellings resolve to the same catalog. Previously, the SDK's exact language comparison returned an empty list for aliases such as `en` and `en_US`. Unsupported languages still return no voices.

Source: [StepFun official voice catalog](https://platform.stepfun.com/docs/zh/guides/developer/tts#官方音色清单), checked 2026-09-20. The [StepAudio 3 TTS model page](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-tts) links to this shared catalog; the catalog's model-compatibility column currently lists older TTS models. The IDs below match the documented catalog, but each voice's live StepAudio 3 synthesis compatibility has not been independently verified.

| Voice | Voice ID |
| --- | --- |
| Vibrant Youth | `vibrant-youth` |
| Lively Girl | `lively-girl` |
| Soft-spoken Gentleman | `soft-spoken-gentleman` |
| Magnetic-voiced Male | `magnetic-voiced-male` |
| 自信男声 | `zixinnansheng` |
| 气质温婉 | `elegantgentle-female` |
| 活力轻快 | `livelybreezy-female` |
| 温柔男声 | `wenrounansheng` |
| 温柔公子 | `wenrougongzi` |
| 元气男声 | `yuanqinansheng` |
| 经典女声 | `jingdiannvsheng` |
| 温柔熟女 | `wenroushunv` |
| 甜美女声 | `tianmeinvsheng` |
| 清纯少女 | `qingchunshaonv` |
| 磁性男声 | `cixingnansheng` |
| 元气少女 | `yuanqishaonv` |
| 邻家姐姐 | `linjiajiejie` |
| 正派青年 | `zhengpaiqingnian` |
| 青年大学生 | `qingniandaxuesheng` |
| 播音男声 | `boyinnansheng` |
| 儒雅男士 | `ruyananshi` |
| 深沉男音 | `shenchennanyin` |
| 亲切女声 | `qinqienvsheng` |
| 温柔女声 | `wenrounvsheng` |
| 机灵少女 | `jilingshaonv` |
| 软萌女声 | `ruanmengnvsheng` |
| 优雅女声 | `youyanvsheng` |
| 冷艳御姐 | `lengyanyujie` |
| 爽快姐姐 | `shuangkuaijiejie` |
| 文静学姐 | `wenjingxuejie` |
| 邻家妹妹 | `linjiameimei` |
| 知性姐姐 | `zhixingjiejie` |
| 爽快男声 | `shuangkuainansheng` |
| 干练女声 | `ganliannvsheng` |
| 亲和女声 | `qinhenvsheng` |
| 活力女声 | `huolinvsheng` |
