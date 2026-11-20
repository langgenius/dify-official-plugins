# Overview

- [Configure](#configure)

Gemini is a family of multimodal AI models from Google, designed to process and generate various types of data, including text, images, audio, and video. This plugin provides access to Gemini models via a single API key, enabling developers to build versatile multimodal AI applications.

## Gemini 4

Carbon, Neon, Hydrogen, and Argon accept text, images, audio, video, and PDFs.
All four models return text and support function calling, structured output, Google Search, URL context, and code execution.
Carbon, Neon, and Argon require a paid API key.
They share a 1,048,576-token window across input, thinking, and output.
The output limit defaults to 65,536 tokens. Raising it enables automatic continuation within the remaining context.
The plugin allows 15 minutes per API request.

| Model | Default thinking | Other levels | Standard input / output per million tokens (USD) |
| --- | --- | --- | --- |
| Carbon, Argon | Medium | Low, High | 2 / 10 through November 30, 2026, then 4 / 20 |
| Neon | High | Low, Medium, Xhigh | 3 / 15 |
| Hydrogen | High | Low, Medium, Xhigh | 1.50 / 7.50 |

Implicit cache reads cost 5% of the input rate. Output includes thinking tokens. [Model pricing](https://aistudio.google.com/docs/pricing) · [Long decode](https://aistudio.google.com/docs/long-decode)

## Configure
After installing the Gemini plugin, configure it with your API key, which you can get from Google. Enter the key in the Model Provider settings and save.

![](./_assets/gemini-01.png)

If you use `url` mode for `MULTIMODAL_SEND_FORMAT` in gemeni and other vision models meantime, you can set `Files URL` to gain better performance.

`Enable request metadata` is optional and disabled by default. Turning it on attaches `dify_app_id` and `dify_source` to each Gemini request as `labels` on `GenerateContentConfig`, so usage can be attributed to a specific Dify app in Cloud Billing. The opt-in applies to the `generate_content` route only; the Interactions API does not surface labels in its billing breakdown and is intentionally left untouched. The Dify session lookup is best-effort: if the session context is not initialized, no labels are attached and the request is sent unchanged.

