# ERNIE Image

A Dify tool that generates images with Baidu's ERNIE Image models through the
[AI Studio](https://aistudio.baidu.com) OpenAI-compatible Images API.

> Localized docs: [简体中文](readme/README_zh_Hans.md) · [日本語](readme/README_ja_JP.md)

## Samples

Generated with `ernie-image-turbo` at the legacy-compatible 1280×720 size:

![ERNIE Image Turbo sample, 1280x720](_assets/samples/sample_turbo_1280x720.jpg)

## Models

| Model | Official model guidance |
|-------|-------------------------|
| `ernie-image-turbo` | Distilled model optimized for speed and aesthetics; typically uses 8 inference steps. This remains the plugin default. |
| `ernie-image` | SFT model focused on general capability and instruction fidelity; typically uses 50 inference steps. |

The hosted API controls inference settings. The step counts above describe the
official model releases and are not plugin parameters.

## Setup

1. Sign in at <https://aistudio.baidu.com> and create an access token from
   *Personal Center → Access Token*.
2. In Dify, install this plugin and authorize it with that token.

## Parameters

- `prompt` *(required)* – text description of the image, up to 2048 characters.
- `model` – `ernie-image-turbo` (default) or `ernie-image`.
- `size` – one of the current official resolutions: `1024x1024`, `848x1264`,
  `768x1376`, `896x1200`, `1264x848`, `1376x768`, or `1200x896`. Default
  `1024x1024`; Baidu recommends `1376x768`. Previously exposed resolutions
  remain accepted by the runtime so saved Dify workflows continue to work.
- `n` – number of images, 1 to 4. Default `1`.
- `seed` – optional integer for reproducibility.
- `watermark` – add a model watermark to the output. Default `false`.

`n` and `seed` are compatibility extensions of the AI Studio endpoint. The
current public Qianfan request schema documents `prompt`, `model`, `size`, and
`watermark`.

The tool emits each successfully downloaded image as a PNG blob and returns a
JSON summary containing the response `id`, `created`, AI Studio `trace_id`,
source URLs, and revised prompts. Baidu documents generated URLs as valid for
24 hours, so use the emitted blobs for durable workflow output.

## Compatibility and validation

- Model, size, prompt length, image count, and integer seed are validated before
  the request.
- Both AI Studio (`errorCode` / `errorMsg`) and current OpenAI-compatible
  (`code` / `message` / `type`) error responses are surfaced.
- A failed image download only skips that image; other images and the JSON
  summary are preserved.

## Official references

- [ERNIE-Image official model card](https://aistudio.baidu.com/modelsdetail/46031)
- [ERNIE-Image-Turbo official model card](https://aistudio.baidu.com/modelsdetail/46030/intro)
- [ERNIE-Image-Turbo API reference](https://cloud.baidu.com/doc/qianfan-api/s/Imo9g5a6a)
