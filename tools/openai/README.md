# OpenAI Tools

Generate and edit images or run background research from Dify workflows, chatflows, and agents.
One OpenAI provider configuration supplies credentials to all tools in this plugin.

## Setup

1. Create an API key in the [OpenAI Platform](https://platform.openai.com/api-keys).
2. Install the **OpenAI** tools plugin in Dify and authorize it with the credentials below.
3. Add a tool to your application, configure its model and options, and bind its inputs to workflow variables.
4. Connect image files or research text to your application's output or a subsequent node.

| Credential | Required | Usage |
| --- | --- | --- |
| OpenAI API key | Yes | Used by every image and research tool. |
| OpenAI base URL | No | Leave blank for OpenAI, or enter the base URL of a compatible service. |
| OpenAI organization ID | No | Supply an organization ID when needed for your account. |

Custom base URLs have trailing slashes removed and `/v1` appended unless they already end in `/v1`.
For example, `https://api.example.com/` becomes `https://api.example.com/v1`.
Credential validation lists models; successful authorization does not establish access to every model or endpoint.
GPT Image access may require [OpenAI organization verification](https://developers.openai.com/api/docs/guides/image-generation).

## Tools

| Tool | Model selection | Operation |
| --- | --- | --- |
| GPT Image 2 / 2.5 Generate | GPT Image 2, GPT Image 2.5 Flare, GPT Image 2.5 Sunburst | Generate images from a prompt. |
| GPT Image 2 / 2.5 Edit | GPT Image 2, GPT Image 2.5 Flare, GPT Image 2.5 Sunburst | Edit or combine reference images, optionally using a mask. |
| GPT Image Generate | `gpt-image-1`, `gpt-image-1-mini` | Generate images with the GPT Image 1 family. |
| GPT Image Edit | `gpt-image-1`, `gpt-image-1-mini` | Edit reference images with the GPT Image 1 family. |
| Deep Research | `o3-deep-research`, `o4-mini-deep-research` | Start, retrieve, or cancel a research task. |
| DALL-E 2 | `dall-e-2` | Legacy image generation. |
| DALL-E 3 | `dall-e-3` | Legacy image generation. |

DALL-E 2 and DALL-E 3 remain registered in the plugin, but OpenAI removed both models from its API on May 12, 2026.
Use the GPT Image tools for OpenAI image requests.
See the [official deprecation notice](https://developers.openai.com/api/docs/deprecations#2025-11-14-dalle-model-snapshots).

## GPT Image 2 and 2.5

### Model selection

Both tools default to `gpt-image-2`.
Choose a GPT Image 2.5 model explicitly in the **Model** field to use the new models introduced with [ChatGPT Images 2.5](https://openai.com/index/introducing-chatgpt-images-2-5/) on September 8, 2026.

| API model ID | Use case | Published snapshot |
| --- | --- | --- |
| `gpt-image-2` | Existing GPT Image 2 generation and editing. | `gpt-image-2-2026-04-21` |
| [`gpt-image-2.5-flare`](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare) | Fast, high-quality generation and editing. | `gpt-image-2.5-flare-2026-09-08` |
| [`gpt-image-2.5-sunburst`](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst) | Detailed creative work and precise editing. | `gpt-image-2.5-sunburst-2026-09-08` |

The model selector uses the API model IDs; the snapshot IDs are reference metadata.
The Generate tool sends a text prompt to the Images API, while Edit sends a prompt and image files.
For another editing pass, feed a previous image output into the next Edit call.

### Parameters

| Parameter | Default | Values and behavior |
| --- | --- | --- |
| `prompt` | Required | Describe the image to create or the changes to make. |
| `model` | `gpt-image-2` | One of the API model IDs listed above. |
| `size` | `auto` | Automatic dimensions or a `WIDTHxHEIGHT` string meeting the limits below. |
| `quality` | `auto` | `auto`, `low`, `medium`, `high`; GPT Image 2.5 also accepts `xhigh` and `max`. |
| `n` | `1` | Integer from 1 to 10. |
| `background` | `auto` | `auto`, `opaque`, or `transparent`. |
| `output_format` | `auto` | `auto`, `png`, `jpeg`, or `webp`; `auto` uses the API's default PNG output. |
| `output_compression` | `100` | Integer from 0 to 100, sent only for explicit JPEG or WebP output. |
| `moderation` | `auto` | Generate only: `auto` or `low`. |
| `image` | Required for Edit | One or more Dify image files, up to 16. |
| `mask` | Unset | Edit only: an optional PNG mask for localized changes. |

Custom dimensions must satisfy all of these conditions:

- Width and height are positive multiples of 16, with neither edge above 3840 pixels.
- The aspect ratio is between 1:3 and 3:1.
- The total pixel count is between 655,360 and 8,294,400.

Common sizes include `1024x1024`, `1536x1024`, and `1024x1536`.
Sizes above `2560x1440` are experimental.
Transparent backgrounds require PNG or WebP; selecting JPEG with `transparent` returns a validation error.
Transparent output is supported by both GPT Image 2.5 models and is in preview for GPT Image 2.
For masked edits, use a mask matching the first input image's dimensions, with transparent areas indicating where to edit.
See the [image generation guide](https://developers.openai.com/api/docs/guides/image-generation) for input-file requirements and mask behavior.

Example settings for a Generate node:

```yaml
model: gpt-image-2.5-flare
prompt: A studio product photo of a ceramic mug, isolated on a transparent background.
size: 1024x1024
quality: high
background: transparent
output_format: webp
output_compression: 90
n: 1
```

### Outputs and usage

Each generated image is returned as a file with its MIME type.
When OpenAI supplies usage, each file also carries `token_usage` metadata and the tool emits a JSON payload such as:

```json
{
  "data": [
    {
      "model": "gpt-image-2.5-flare",
      "operation": "generate",
      "image_count": 1,
      "usage": {
        "total_tokens": 1200,
        "input_tokens": 200,
        "output_tokens": 1000,
        "input_tokens_details": {"text_tokens": 200, "image_tokens": 0}
      }
    }
  ]
}
```

These token counts are illustrative.
Usage belongs to the entire request, so do not sum the same usage metadata across its image files.
The JSON payload is omitted when the API returns no usage information.

At launch, both GPT Image 2.5 models use the following USD rates per million tokens:

| Token category | Input | Cached input | Output |
| --- | --- | --- | --- |
| Text | $5 | $1.25 | — |
| Image | $8 | $2 | $30 |

The plugin reports tokens rather than calculating a monetary charge.
GPT Image 2 per-image estimates do not apply to GPT Image 2.5 because token consumption can differ.
Check [OpenAI pricing](https://developers.openai.com/api/docs/pricing) for current rates.

## GPT Image 1 tools

**GPT Image Generate** and **GPT Image Edit** default to `gpt-image-1` and also offer `gpt-image-1-mini`.
Both accept `auto`, `1024x1024`, `1536x1024`, or `1024x1536` sizes; `auto`, `low`, `medium`, or `high` quality; and 1–10 output images.
Generate additionally exposes background, output format, JPEG/WebP compression, and moderation controls.
Edit accepts reference image files and an optional mask, with output settings determined by the API beyond size and quality.
Both return image files; the separate usage JSON described above is specific to the GPT Image 2 / 2.5 tools.

## Deep Research

Deep Research uses the Responses API and always starts tasks in background mode.
Select `o3-deep-research` (the default) or `o4-mini-deep-research`.
The plugin exposes web search and code interpreter, both enabled by default.
Keep web search enabled for OpenAI research requests: it supplies the research source, while code interpreter adds data analysis.
See the [official Deep Research guide](https://developers.openai.com/api/docs/guides/deep-research).

### Task lifecycle

| Action | Required inputs | Result |
| --- | --- | --- |
| `start` | `prompt` | Starts a task and returns confirmation text plus JSON containing `response_id` and `status`. |
| `retrieve` | `response_id` | Returns the current status, or the report once the task is completed. |
| `cancel` | `response_id` | Requests cancellation and returns the resulting status. |

1. Call `start` with a research prompt specifying the question, preferred sources, and desired output.
2. Save the returned JSON `response_id` in a workflow variable or application state.
3. Call `retrieve` with that ID again while the status is `queued` or `in_progress`.
4. On `completed`, use the tool's text output as the report; handle `failed`, `cancelled`, and `incomplete` as terminal statuses.

Each invocation makes one API request; the tool does not automatically poll or wait for a report.
Use `cancel` with the same ID to request that a running task stop.

### Options and outputs

`max_tool_calls` optionally limits tool calls during research.
`timeout` controls each API request in seconds and defaults to 3600 when unset; it is not a research-task duration limit.
The form also exposes `temperature` (default `1`), `reasoning_effort` (default `medium`), and `summary` (default `auto`), which are forwarded when supplied and subject to the selected model's API support.

Completed reports are returned as text, with numbered links and a reference list when URL citations are present.
The accompanying JSON contains response metadata rather than the report body: `response_id`, `status`, `model`, and, when available, `background`, `tools`, `max_tool_calls`, `reasoning_effort`, `summary`, `research_process`, `usage`, and `error`.
`research_process` can include web-search actions, code-interpreter activity, and reasoning-summary text.
The top-level `summary` field describes the reasoning-summary setting, not a summary of the report.
Failed tasks return JSON with `response_id`, `status`, and `error.code` / `error.message`.
Input validation failures and API request errors may return only a text message, so inspect text output as well as JSON.

## Local development

The plugin runner uses Python 3.12.
Install the locked dependencies from the repository root:

```bash
uv sync --project tools/openai --frozen --python 3.12
```

Run the OpenAI tool regression checks:

```bash
uv run --project tools/openai --frozen --with pytest pytest -q tests/tools/openai/test_openai_tool.py
```

The tests mock API calls and do not generate billable images or research tasks.
Dependency constraints live in [pyproject.toml](./pyproject.toml), resolved versions in [uv.lock](./uv.lock), and plugin release metadata in [manifest.yaml](./manifest.yaml).
