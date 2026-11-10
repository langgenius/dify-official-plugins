# Overview

- [Configure](#configure)

Gemini is a family of multimodal AI models from Google, designed to process and generate various types of data, including text, images, audio, and video. This plugin provides access to Gemini models via a single API key, enabling developers to build versatile multimodal AI applications.

## Gemini 4 Argon

Select `gemini-4-argon` with a paid Gemini API key.
It accepts text, images, audio, video, and PDFs, with text output, function calling, structured output, Google Search, URL context, and code execution.
Input, thinking, and output share a 1,048,576-token context window.
Thinking defaults to Medium, with Low and High also available.
The output limit defaults to 65,536 tokens; raising it enables the Google GenAI SDK's automatic continuation, up to the remaining context window.
The plugin allows 15 minutes per request; configure the Dify deployment's timeouts to accommodate long reasoning tasks.

Standard introductory pricing is $2 per million input tokens and $10 per million output tokens, including thinking, through November 30, 2026.
Google's published rates become $4 and $20 respectively on December 1, 2026; the plugin's price metadata will need updating then.
Implicit caching is supported by Google; explicit context caching is unavailable for this model.
See the [release announcement](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-4-argon/), [model specifications](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon), [long decode guide](https://ai.google.dev/gemini-api/docs/generate-content/long-decode), and [pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon).

## Configure
After installing the Gemini plugin, configure it with your API key, which you can get from Google. Enter the key in the Model Provider settings and save.

![](./_assets/gemini-01.png)

If you use `url` mode for `MULTIMODAL_SEND_FORMAT` in gemeni and other vision models meantime, you can set `Files URL` to gain better performance.

`Enable request metadata` is optional and disabled by default. Turning it on attaches `dify_app_id` and `dify_source` to each Gemini request as `labels` on `GenerateContentConfig`, so usage can be attributed to a specific Dify app in Cloud Billing. The opt-in applies to the `generate_content` route only; the Interactions API does not surface labels in its billing breakdown and is intentionally left untouched. The Dify session lookup is best-effort: if the session context is not initialized, no labels are attached and the request is sent unchanged.

