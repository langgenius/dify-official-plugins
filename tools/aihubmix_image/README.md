# AIHubMix Image

**Author:** AIHubMix

**Version:** 0.2.1

**Type:** Dify Plugin

## Overview

Two tools — **Generate Image** and **Edit Image** — that reach the image models AIHubMix serves
through the gateway's unified image endpoint: GPT Image, Gemini, Qwen-Image, Wan, GLM, Agnes.

There is no per-model tool. The model dropdown is filled from the gateway with your API key,
and each model's accepted parameters are read from its published schema at call time, so a
model added to AIHubMix shows up without a plugin update.

## Which models you get

Whatever AIHubMix serves at the moment you open the dropdown — the latest GPT Image, Gemini,
Qwen Image, Wan, GLM and Agnes releases among them, plus anything the gateway adds later. This
README deliberately does not reproduce the list: it would be stale the week a new model lands,
and the dropdown is the authoritative copy.

*Generate Image* offers every image model the gateway marks as schema-verified; *Edit Image*
narrows that to the ones that accept a source image (a text-only model such as GLM Image is
left out). Every model on the list at release time was called end to end against the live
gateway.

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

The model on each node comes from the gateway now, not from the plugin, so a few ids 0.1.x could
call are no longer offered: `imagen-4.0`, `FLUX-1.1-pro`, `dall-e-3`, `gpt-image-1.5` and the
Ideogram aliases have no verified unified-endpoint schema. Pick the nearest current model from
the dropdown instead — Gemini for Imagen, GPT Image for DALL·E.

## Credentials

* **API Key** — get one at [https://console.aihubmix.com/token](https://console.aihubmix.com/token)
* **API Base URL** — `https://api.inferera.com` (default) or `https://aihubmix.com`

## Notes

* Generated artifacts are kept by the gateway for two hours. The plugin downloads them during
  the call, so this only matters if you re-run a very old task.
* Generation can take a few minutes on large sizes; the plugin polls until the task reaches a
  terminal state and reports the task id if it does not settle in time.
* A few models make an otherwise optional field mandatory (*Size*, for instance). That is read
  from the model's own schema, so the plugin says which field is missing before spending a call
  rather than letting the gateway reject the request.
* If the gateway cannot be reached the dropdown reports the error rather than falling back to
  a frozen list, so it never silently offers a model that is no longer served.

## Privacy Policy

See [PRIVACY.md](PRIVACY.md).
