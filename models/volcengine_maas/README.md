# Volcengine Ark (MaaS / Endpoint)

Use Volcengine Ark endpoints ("Endpoint ID") in Dify.

This plugin is a good fit when you:
- already created an **Ark Endpoint** (e.g., a deployed base model / fine-tuned model / embedding endpoint), and
- want to call it from Dify using **AK/SK** (IAM) or **Ark API Key** authentication.

If you want to call Ark **base models directly** without creating endpoints, use the **Volcengine Ark (Direct)** provider instead.

## Configure

1. Prepare credentials in Volcengine Console:
   - **AK/SK (Recommended)**: https://console.volcengine.com/iam/keymanage/
   - **Ark API Key**: https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey
2. Create an Ark Endpoint and copy its **Endpoint ID**.
3. In Dify, go to **Settings -> Model Provider -> Volcengine Ark (Endpoint)**.
4. Click **Add Model**, fill in the fields, and save.

### DeepSeek V4.1 Flash and GLM 5.3 Flash

Select `DeepSeek-V4.1-Flash` (model version `deepseek-v4-1-flash-260910`) or
`GLM-5.3-Flash` (model version `glm-5-3-flash-260828`) for the matching endpoint,
and enter its `ep-...` Endpoint ID. Both models support text, image, and video
input, tool calls, and a 1M context window. DeepSeek supports up to 384K output
tokens; GLM supports up to 128K.

DeepSeek exposes the thinking switch and reasoning effort
`none` / `low` / `high` / `max` (default `high`; `none` disables thinking).
GLM always enables thinking and supports `low` / `high` / `max` (default `max`).

Specifications checked on 2026-10-10:
[DeepSeek V4.1 Flash](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=deepseek-v4-1-flash),
[GLM 5.3 Flash](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=glm-5-3-flash).
Token pricing uses DeepSeek's peak rate (RMB 2 input / 8 output per million tokens;
off-peak is RMB 1 / 4), and GLM's standard rate (RMB 0.8 / 2.8).

### Seed 2.1 and DeepSeek V4 GA

Select the base model matching your deployed endpoint:

| Base Model | Model version | Context / max output tokens |
| --- | --- | --- |
| Doubao-Seed-2.1-pro | doubao-seed-2-1-pro-260628 | 256K / 256K |
| Doubao-Seed-2.1-turbo | doubao-seed-2-1-turbo-260628 | 256K / 256K |
| Doubao-Seed-2.1-lite | doubao-seed-2-1-lite-260915 | 1M / 256K |
| DeepSeek-V4-Pro-GA | deepseek-v4-pro-ga-260813 | 1M / 384K |
| DeepSeek-V4-Flash-GA | deepseek-v4-flash-ga-260731 | 1M / 384K |

Continue to enter your `ep-...` Endpoint ID. Seed 2.1 supports image/video input,
structured output, and reasoning effort from `minimal` to `high` (default `high`).
DeepSeek V4 GA supports text input and reasoning effort up to `max`.

Seed 2.1 Lite also supports audio input via a public URL or Base64 data.
Its standard text/image/video token prices are RMB 0.8 input / 2.7 output per
million tokens. Audio input costs RMB 12 per million tokens; Dify's single
input-token price only estimates the standard input rate.
[Seed 2.1 Lite specifications](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed-2-1-lite)
checked on 2026-10-10.

Specifications and standard online token prices checked on 2026-09-07:
[Seed 2.1 Pro](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed-2-1-pro),
[Seed 2.1 Turbo](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=doubao-seed-2-1-turbo),
[DeepSeek V4 Pro GA](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=deepseek-v4-pro-ga),
[DeepSeek V4 Flash GA](https://console.volcengine.com/ark/region:cn-beijing/model/detail?name=deepseek-v4-flash-ga).

![img.png](_assets/img.png)

## Troubleshooting | 常见问题

- **401/403**: invalid credentials, wrong region, or your account has no permission for the endpoint.
- **404 / model not found**: `endpoint_id` is incorrect or not available in the selected region.
- **Invalid URL**: `api_endpoint_host` must include `/api/v3`.
- **Timeout / connection error**: ensure your Dify deployment can reach Volcengine endpoints.
