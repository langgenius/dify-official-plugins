# AIHubMix Image

**Author:** AIHubMix

**Version:** 0.2.0

**Type:** Dify Plugin

## Overview

Two tools — **Generate Image** and **Edit Image** — that reach the image models AIHubMix serves
through the gateway's unified image endpoint: GPT Image, Gemini, Qwen-Image, GLM, Wan, Agnes.

There is no per-model tool. The model dropdown is filled from the gateway with your API key,
and each model's accepted parameters are read from its published schema at call time, so a
model added to AIHubMix shows up without a plugin update.

## What that means in practice

* **The model list is live.** It is the gateway's own catalog, narrowed to the models whose
  unified-endpoint schema the gateway has verified (`schema_checked`) — the plugin keeps no
  hand-written list of its own, so a newly verified model appears on its own and a withdrawn
  one disappears. The edit tool further narrows it to models that accept an image as input.
* **Parameters are validated against the model you picked.** A value the model does not allow
  is rejected with the list of values it does allow, instead of a bare HTTP 400 from the
  gateway. A parameter the model does not have at all is dropped and reported in the output
  (`agnes-image-2.1-flash`, for example, has no `n` and rejects the whole request if it is sent).
* **Images come back as files.** The plugin downloads the artifact with your key and hands
  Dify the bytes, with the real image type detected from the file contents.
* **Long-tail parameters have an escape hatch.** The *Advanced Parameters (JSON)* field takes
  a JSON object such as `{"quality": "high"}` or `{"watermark": false}`; each key is routed to
  wherever the selected model declares it.

## Tools

### Generate Image

Text to image. Optional reference images for models that accept image input.

Parameters: model, prompt, reference images, number of images, size, aspect ratio, output
format, seed, negative prompt, advanced parameters.

### Edit Image

Image to image: editing, restyling, multi-image composition, and inpainting with a mask on
models that support one.

Parameters: model, prompt, source images, mask, number of images, size, aspect ratio, output
format, seed, negative prompt, advanced parameters.

## Upgrading from 0.1.x — breaking change

0.1.x shipped sixteen per-model tools (`gpt-image`, `qwen-image`, `imagen`, `flux-kontext`,
`ideogram`, `wan`, …). They are all replaced by the two tools above, so **every workflow node
using an old tool has to be repointed** at *Generate Image* or *Edit Image* and have its model
picked from the dropdown.

Which models you get is decided by the gateway, not by the plugin: the dropdown carries every
active image model the gateway marks as schema-verified. At the time of writing that is
thirteen for *Generate Image* — `gpt-image-2`, `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst`,
`gemini-2.5-flash-image`, `gemini-3-pro-image`, `gemini-3.1-flash-image`,
`gemini-3.1-flash-lite-image`, `qwen-image-2.0`, `qwen-image-2.0-pro`, `wan2.7-image`,
`wan2.7-image-pro`, `glm-image`, `agnes-image-2.1-flash` — and twelve for *Edit Image*
(all but `glm-image`, which is text-only). Models 0.1.x could call that are not verified,
including `imagen-4.0`, `FLUX-1.1-pro`, `dall-e-3`, `gpt-image-1.5` and the Ideogram aliases,
are not offered; the nearest verified equivalents are `gemini-3-pro-image` and `gpt-image-2`.

## Credentials

* **API Key** — get one at [https://console.aihubmix.com/token](https://console.aihubmix.com/token)
* **API Base URL** — `https://api.inferera.com` (default) or `https://aihubmix.com`

## Notes

* Generated artifacts are kept by the gateway for two hours. The plugin downloads them during
  the call, so this only matters if you re-run a very old task.
* Generation can take a few minutes on large sizes; the plugin polls until the task reaches a
  terminal state and reports the task id if it does not settle in time.
* `agnes-image-2.1-flash` is the one model that makes *Size* mandatory; the plugin says so
  before spending a call.
* If the gateway cannot be reached the dropdown reports the error rather than falling back to
  a frozen list, so it never silently offers a model that is no longer served.

## Privacy Policy

See [PRIVACY.md](PRIVACY.md).
