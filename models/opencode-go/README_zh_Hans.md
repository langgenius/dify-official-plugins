# OpenCode Go

[Dify](https://dify.ai) 的 [OpenCode Go](https://opencode.ai/v2/docs/console/go) 模型供应商插件。

OpenCode Go 是订阅制网关，提供精选开源编码模型，分两档套餐：**Go**（$10/月）与 **Go Plus**（$40/月）—— token 单价相同，仅月度限额不同。本插件将这些模型以单一供应商形式接入 Dify。

## 功能

- 预置 OpenCode Go 目录中的模型（GLM、Kimi、DeepSeek、MiMo、MiniMax、Qwen、LongCat（含 LongCat 2.5）、Claude、Hy、Grok、GPT Luna、Muse Spark、Space Bunny）
- 自定义模型支持，并提供 **API 协议** 选择（`chat` / `anthropic` / `responses`）
- 同一供应商内完整支持三类上游协议：
  - **Chat Completions**（`{base}/chat/completions` + `Authorization: Bearer`）— 多数模型默认
  - **Anthropic Messages**（`{base}/messages` + `x-api-key`）— 仅 `/messages` 可用的模型（如 `minimax-m2.7`、`claude-haiku-5-5`）
  - **OpenAI Responses**（`{base}/responses` + `Authorization: Bearer`）— 仅 `/responses` 可用的模型（如 `grok-4.7`、`grok-4.6`、`gpt-6-luna`、`gpt-5.6-luna`、`muse-spark-*`）
- **三条协议路径都会**发送 OpenCode 必需请求头：
  - `User-Agent`（默认 `dify-opencode-go-plugin/0.5.0`）
  - `x-opencode-session`（会话路由 / prompt cache）
- 上游怪癖已自动处理：
  - `kimi-k2.7-code` — 强制 `temperature=1` / `top_p=0.95`（网关仅接受这两组值）
  - `gpt-5.6-luna` — 剥离 `temperature` / `top_p`（上游直接拒绝）
  - 瞬时 `502` / `503` / `529` 自动退避重试；空 SSE / 裸错误 JSON 会映射为 Dify `InvokeError`（不会静默返回空文本）
  - SSE 强制按 UTF-8 解码（OpenCode 常不声明 charset）
  - 出站请求遵循进程 / 系统代理（`trust_env`）
- **会话隔离（推荐）**：开启 LLM 节点模型参数 `extra_headers` 并保留默认 JSON。Dify 会在调用前解析 `{{#sys.*#}}`；插件随后选择：
  - Chatflow / 对话应用：会话 ID → 同一对话共用一个 session
  - 工作流应用：通过内部辅助头取 `workflow_run_id` → 同一次运行共用一个 session

```json
{
  "x-opencode-session": "{{#sys.conversation_id#}}",
  "x-dify-run-id": "{{#sys.workflow_run_id#}}"
}
```

- 未配置 `extra_headers` 或解析结果为空时的回退顺序：
  1. 供应商凭证 `session_id`（可选静态覆盖）
  2. 插件 Session 中的 `conversation_id`（Dify 提供时）
  3. 按次隔离（RPC session id 或随机 UUID）— 不会粘在 Dify 用户 ID 上
- 未解析的 Dify 模板（`{{#sys.*#}}`）绝不会被当作 session 发送。
- 内部辅助头 `x-dify-run-id` 绝不会外发。
- 默认 Base URL：`https://opencode.ai/zen/go/v1`

## 套餐与用量限制

两档订阅 —— **Go**（$10/月）与 **Go Plus**（$40/月）—— token 单价相同，仅月度限额不同。限额按滚动窗口执行：

| 窗口 | 占月度限额比例 |
| --- | ---: |
| 5 小时 | 20% |
| 周 | 50% |
| 月 | 100% |

超出限额后，若 OpenCode Console 开启了 **"Use balance"** 选项且账户有余额，请求可回退到按量付费余额继续。

## 使用步骤

1. 在 [opencode.ai/auth](https://opencode.ai/auth) 订阅 OpenCode Go 并复制 API Key。
2. 在 Dify 中安装本插件（市场 / 本地包 / 远程调试）。
3. 打开 **设置 → 模型供应商 → OpenCode Go**，粘贴 API Key 并保存。
4. 在应用中选择 OpenCode Go 模型。

### 自定义模型

若 OpenCode 新增模型而插件尚未收录：

1. 在 OpenCode Go 下添加自定义模型。
2. **模型 ID** 填写 [Go 文档](https://opencode.ai/v2/docs/console/go) 中的 model id（例如 `kimi-k2.6`）。
3. **显示名称**（可选）= 模型列表中展示的名称，默认与模型 ID 相同。
4. 设置 **API 协议** 与模型端点一致：
   - `chat`（默认）→ `/chat/completions`
   - `anthropic` → `/messages`（`minimax-m2.7`、`claude-haiku-5-5` 等仅 Messages 可用的模型）
   - `responses` → `/responses`（`grok-4.7`、`grok-4.6`、`gpt-5.6-luna`、`muse-spark-*`）
5. 按需配置能力开关：
   - **思考模式**（默认开启）— 暴露思考参数（`enable_thinking`、`thinking_budget`、`reasoning_effort`）
   - **视觉 / 音频 / 视频 / 文档** — 多模态输入
   - **结构化输出** — 暴露 `response_format` / `json_schema`
6. 可按需设置上下文长度、最大 token、Function Calling。

## 协议矩阵

| 协议 | 端点 | 认证 | Session | UA |
| --- | --- | --- | --- | --- |
| chat | `{base}/chat/completions` | `Authorization: Bearer` | 必须 | 必须 |
| anthropic | `{base}/messages` | `x-api-key` + `anthropic-version: 2023-06-01` | 必须 | 必须 |
| responses | `{base}/responses` | `Authorization: Bearer` | 必须 | 必须 |

### 自定义模型表单（0.4.0）

添加自定义模型时可配置：

| 字段 | 作用 |
| --- | --- |
| **模型 ID** | 上游模型 id（必填） |
| **显示名称** | 列表中展示名称（可选，默认同模型 ID） |
| **思考模式** | 默认开启。启用 `agent-thought` 并暴露思考参数 |
| **视觉 / 音频 / 视频 / 文档** | 多模态输入 |
| **结构化输出** | 暴露 `response_format` / `json_schema` |
| **API 协议** | `chat` / `anthropic` / `responses` |
| Function Calling / 上下文 / 最大 token | 同前 |

### 0.5.0 新增预置模型

| 模型 | 协议 | 说明 |
| --- | --- | --- |
| Claude Haiku 5.5（`claude-haiku-5-5`） | anthropic | 仅 Messages（`/messages`）。基础价 $0.10 / $0.50（输入 ≤ 100K）；长上下文阶梯 > 100K $0.50 / $2.50。上下文 1M，最大输出 128K。提示词**不用于训练**，数据保留 30 天。官网目录与 provider 页已收录，但截至 2026-10-08 网关 `/v1/models` 尚未返回该 id（可能需绑定计费）。**尚未冒烟。** |
| LongCat 2.5 Preview Free（`longcat-2.5-preview-free`） | chat | **限时免费**（活动期 Unlimited），可能随时下线。上下文 1M，最大输出 131,072。请勿作为生产长期依赖。 |
| Space Bunny（`space-bunny`） | chat | 由 `space-bunny-free` 更名（见下方移除表），并转为付费：$0.15 / $0.60，缓存读 $0.03，月度限额 $30。 |

### 0.3.0 新增预置模型

| 模型 | 协议 | 说明 |
| --- | --- | --- |
| Grok 4.7（`grok-4.7`） | responses | 与 Grok 4.6 同为仅 Responses。**部分区域（含中国大陆）可能需代理出境** |
| MiMo-V2.6-Flash（`mimo-v2.6-flash`） | chat | 多模态标记对齐 MiMo-V2.5（vision / video / audio） |
| MiMo-V2.6-Pro（`mimo-v2.6-pro`） | chat | 对齐 MiMo-V2.5-Pro |
| GPT 6 Luna（`gpt-6-luna`） | responses | 文档标明仅 Responses。**部分地区受限** |
| Space Bunny Free（`space-bunny-free`） | chat | **限时免费，可能随时下线**。请勿作为生产长期依赖。 |

### 0.2.0 新增预置模型

| 模型 | 协议 | 说明 |
| --- | --- | --- |
| MiniMax M2.7（`minimax-m2.7`） | anthropic | oa-compat `/chat/completions` 会 500；`/messages` 可用 |
| Grok 4.6（`grok-4.6`） | responses | 文档标明仅 Responses。**部分区域（含中国大陆）可能需代理出境** |
| GPT 5.6 Luna（`gpt-5.6-luna`） | responses | 文档标明仅 Responses；**部分地区受限**（通常需代理）。插件会剥离 `temperature` / `top_p` |
| Muse Spark 1.3 Contributor | responses | **区域限制**（Meta 地理政策）；Contributor 档可能用于训练 |
| Muse Spark 1.2 Contributor | responses | 同上 |

> **代理说明：** Responses 线模型常见地域限制。在中国大陆使用时，请先设置
> `HTTP_PROXY` / `HTTPS_PROXY`（或打开系统代理），再启动插件 / Dify 运行时。
> 插件会遵循进程 / 系统代理环境变量（`trust_env`）。

Qwen 以及 MiniMax M3 继续走 Chat Completions（oa-compat）。OpenCode 文档虽列出 `/messages`，但 oa-compat 实测 200，保持可避免回归。MiniMax M2.7 是例外（chat 500 → 走 anthropic）。

### 0.5.0 移除的预置模型

| 模型 | 原因 |
| --- | --- |
| Space Bunny Free（`space-bunny-free`） | 上游将模型 id 更名为 `space-bunny` —— 网关 `/v1/models` 现仅返回 `space-bunny`，`space-bunny-free` 已无法解析。该模型同时转为付费（$0.15 / $0.60）。若你曾以自定义模型方式添加，请用 `space-bunny` 重新创建。 |

### 目录外保留的模型

`glm-5.1`、`qwen3.6-plus`、`qwen3.7-max` 已不再出现在官网 OpenCode Go 目录中，但网关 `/v1/models` 仍可调用、功能正常。插件继续将其作为预置模型保留，以兼容存量业务；若网关后续下线，插件可能在未来版本移除。

### 0.3.0 移除的预置模型

| 模型 | 原因 |
| --- | --- |
| Union Alpha Free（`union-alpha`） | 已不在 OpenCode Go 模型目录中（原限时免费体验）。如网关仍接受该 id，可作为自定义模型继续使用。 |
| MiniMax M2.5（`minimax-m2.5`） | 已从 Go「当前模型列表」/ 用量表中移除，故取消预置。 |

### 下线提醒

| 模型 | 下线时间（北京时间） | 迁移建议 |
| --- | --- | --- |
| `mimo-v2.5` | **2026-10-21 10:00** | 请切换至 `mimo-v2.6-flash` |
| `mimo-v2.5-pro` | **2026-10-21 10:00** | 请切换至 `mimo-v2.6-pro` |

两个模型**仍可正常使用**（未禁用），仅在名称与描述中提示下线时间，避免影响存量业务。请在下线前完成迁移。

### 模型参数约束

| 模型 | 行为 |
| --- | --- |
| `kimi-k2.7-code` | 网关仅接受 `temperature=1` 与 `top_p=0.95`；插件会覆盖其他取值 |
| `gpt-5.6-luna` | 上游拒绝 `temperature` 与 `top_p`；插件会剥离这两个参数 |

### 缓存价与阶梯价（参考）

Dify 的 `PriceConfig` 只记录**基础输入 / 输出**单价（USD / 1M tokens）。OpenCode Go 目录还包含缓存读写价与长上下文阶梯价；这些**不会**进入插件 UI 或计费字段，仅供成本评估参考。数据来源：[OpenCode Go provider 目录](https://models.opencode.ai/providers/opencode-go)（2026-10 快照）。

**缓存价**（网关启用 prompt caching 时）：

| 模型 | 缓存读 | 缓存写 |
| --- | ---: | ---: |
| `claude-haiku-5-5` | $0.01 | $0.125 |
| `deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` / `deepseek-v4.1-flash` | $0.003 | — |
| `deepseek-v4-pro` | $0.022 | — |
| `glm-5.1` / `glm-5.2` / `glm-5.3` | $0.26 | — |
| `glm-5.3-flash` | $0.03 | — |
| `gpt-5.6-luna` | $0.02 | $0.25 |
| `gpt-6-luna` | $0.01 | $0.125 |
| `grok-4.6` / `grok-4.7` | $0.50 | — |
| `hy3` | $0.035 | — |
| `hy4-preview` | $0.042 | — |
| `kimi-k2.6` | $0.16 | — |
| `kimi-k2.7-code` | $0.19 | — |
| `kimi-k3` | $0.30 | — |
| `longcat-2.0` | $0.006 | — |
| `longcat-2.5-preview-free` | 免费 | 免费 |
| `mimo-v2.5` / `mimo-v2.6-flash` | $0.0028 | — |
| `mimo-v2.5-pro` / `mimo-v2.6-pro` | $0.003625 | — |
| `minimax-m2.7` | $0.06 | $0.375 |
| `minimax-m3` | $0.06 | — |
| `muse-spark-1.2-contributor` / `muse-spark-1.3-contributor` | $0.002 | — |
| `qwen3.6-plus` | $0.05 | $0.625 |
| `qwen3.7-plus` | $0.04 | $0.50 |
| `qwen3.7-max` | $0.50 | $3.125 |
| `qwen3.8-flash` | $0.016 | $0.20 |
| `qwen3.8-max` | $0.25 | $2.50 |
| `space-bunny` | $0.03 | — |

**长上下文阶梯价**（输入超过阈值后单价上浮；YAML 始终记录基础档）：

| 模型 | 阈值 | 阶梯 输入 / 输出 | 阶梯 缓存读 / 写 |
| --- | ---: | ---: | ---: |
| `claude-haiku-5-5` | > 100,000 | $0.50 / $2.50 | $0.05 / $0.625 |
| `gpt-5.6-luna` | > 272,000 | $0.40 / $1.80 | $0.04 / $0.50 |
| `gpt-6-luna` | > 272,000 | $0.20 / $0.75 | $0.02 / $0.25 |
| `grok-4.6` / `grok-4.7` | > 200,000 | $4.00 / $12.00 | $1.00 / — |
| `minimax-m3` | > 512,000 | $0.60 / $2.40 | $0.12 / — |
| `qwen3.6-plus` | > 256,000 | $2.00 / $6.00 | $0.20 / $2.50 |
| `qwen3.7-plus` | > 256,000 | $1.20 / $4.80 | $0.12 / $1.50 |

上表未列出的模型在目录中没有缓存或阶梯行（仅有统一基础价）。

**DeepSeek V4 系列峰谷价：** 按时段计价。**Peak（峰时）** = 周一至周五 01:00–04:00 与 06:00–10:00（UTC）；其余时间（含周末）为 **Off-Peak（谷时）**。

| 模型 | 谷时 输入 / 输出 | 峰时 输入 / 输出 |
| --- | ---: | ---: |
| `deepseek-v4.1-flash` | $0.15 / $0.60 | $0.30 / $1.20 |
| `deepseek-v4-pro` | $0.66 / $1.98 | $1.32 / $3.96 |
| `deepseek-v4-flash` | $0.15 / $0.60 | $0.30 / $1.20 |
| `deepseek-v4-flash-vision-exp` | $0.15 / $0.60 | $0.30 / $1.20 |

**隐私要点（2026-10）：** Muse Spark Contributor 系列会用你的提示词训练 Meta 模型，且**非**零数据保留（ZDR）。DeepSeek 的 ZDR 协议已续签至 **2026-10-31**。Grok / GPT / Claude 系列数据保留 30 天；其余模型保留 0 天。

### 多模态能力标记

能力开关（vision / video / document / audio）对齐**官方模型能力**，因为 OpenCode Go 实际是转发上游官方 API。并非每个模型的每种模态都在网关上单独复测过。

本地实测矩阵（2026-09-17，0.2.0 + 实测修复）。所有标记 vision 的模型均已在用户侧 Dify 工作流中验证通过：

| 模型 | 状态 |
| --- | --- |
| glm-5.3-flash / glm-5.x | OK（流式 + 非流式） |
| glm-5.1 / glm-5.2 | OK |
| mimo-v2.6-flash / mimo-v2.6-pro | 0.3.0 新增，尚未冒烟 |
| mimo-v2.5 / mimo-v2.5-pro | OK |
| kimi-k2.6 / kimi-k2.7-code / kimi-k3 | OK |
| qwen3.6-plus / qwen3.7-plus / qwen3.7-max / qwen3.8-flash / qwen3.8-max | OK |
| minimax-m3 | OK（chat） |
| minimax-m2.7 | OK（anthropic `/messages`） |
| deepseek-v4-pro / v4-flash / v4.1-flash / flash-vision-exp | OK |
| longcat-2.0 / hy3 / hy4-preview | OK |
| grok-4.7 经 responses `/responses` | 0.3.0 新增，尚未冒烟 |
| grok-4.6 经 responses `/responses` | 代理下 OK |
| gpt-5.6-luna 经 responses | 代理下 OK |
| muse-spark-1.3 经 responses | HTTP 200（内容质量可能波动；区域受限） |
| claude-haiku-5-5 经 anthropic `/messages` | 0.5.0 新增，尚未冒烟（截至 2026-10-08 网关 `/v1/models` 未返回该 id） |
| longcat-2.5-preview-free | 0.5.0 新增，尚未冒烟 |
| space-bunny | 0.5.0 新增，尚未冒烟（由 `space-bunny-free` 更名） |

## 开发 / 调试

```bash
pip install "dify_plugin>=0.10.0"
```

将 `.env.example` 复制为 `.env`，填入 Dify **插件 → 调试** 中的 key。

```bash
python -m main
```

本地单元测试（无网络）：

```bash
python test_session_id.py
python test_session_runtime.py
python test_extra_headers.py
python test_backward_compat_002.py
python test_protocol_routing.py
python test_custom_model_features.py
```

在线冒烟（需 `OPENCODE_GO_API_KEY`）：

```bash
python test_smoke_live.py
```

打包：

```bash
dify plugin package models/opencode-go -o dist/opencode_go-0.5.0.difypkg
```

## 链接

- OpenCode Go 文档：https://opencode.ai/v2/docs/console/go
- 模型列表 API：`https://opencode.ai/zen/go/v1/models`
- 认证 / API Key：https://opencode.ai/auth
- Dify 插件文档：https://docs.dify.ai/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## 免责声明

本插件为非官方社区插件，与 OpenCode / Anomaly 及 Dify 无隶属关系。
