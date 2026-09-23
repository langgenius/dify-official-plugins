# OpenCode Go

[Dify](https://dify.ai) 的 [OpenCode Go](https://opencode.ai/docs/go/) 模型供应商插件。

OpenCode Go 是 $10/月 的订阅网关，提供精选开源编码模型。本插件将这些模型以单一供应商形式接入 Dify。

## 功能

- 预置 OpenCode Go 目录中的模型（GLM、Kimi、DeepSeek、MiMo、MiniMax、Qwen、LongCat、Hy、Grok、GPT Luna、Muse Spark）
- 自定义模型支持，并提供 **API 协议** 选择（`chat` / `anthropic` / `responses`）
- 同一供应商内完整支持三类上游协议：
  - **Chat Completions**（`{base}/chat/completions` + `Authorization: Bearer`）— 多数模型默认
  - **Anthropic Messages**（`{base}/messages` + `x-api-key`）— 仅 `/messages` 可用的模型（如 `minimax-m2.7`）
  - **OpenAI Responses**（`{base}/responses` + `Authorization: Bearer`）— 仅 `/responses` 可用的模型（如 `grok-4.7`、`grok-4.6`、`gpt-5.6-luna`、`muse-spark-*`）
- **三条协议路径都会**发送 OpenCode 必需请求头：
  - `User-Agent`（默认 `dify-opencode-go-plugin/0.4.0`）
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

## 使用步骤

1. 在 [opencode.ai/auth](https://opencode.ai/auth) 订阅 OpenCode Go 并复制 API Key。
2. 在 Dify 中安装本插件（市场 / 本地包 / 远程调试）。
3. 打开 **设置 → 模型供应商 → OpenCode Go**，粘贴 API Key 并保存。
4. 在应用中选择 OpenCode Go 模型。

### 自定义模型

若 OpenCode 新增模型而插件尚未收录：

1. 在 OpenCode Go 下添加自定义模型。
2. **模型 ID** 填写 [Go 文档](https://opencode.ai/docs/go/) 中的 model id（例如 `kimi-k2.6`）。
3. **显示名称**（可选）= 模型列表中展示的名称，默认与模型 ID 相同。
4. 设置 **API 协议** 与模型端点一致：
   - `chat`（默认）→ `/chat/completions`
   - `anthropic` → `/messages`（`minimax-m2.7` 等仅 Messages 可用的模型）
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

### 0.3.0 新增预置模型

| 模型 | 协议 | 说明 |
| --- | --- | --- |
| Grok 4.7（`grok-4.7`） | responses | 与 Grok 4.6 同为仅 Responses。**部分区域（含中国大陆）可能需代理出境** |
| MiMo-V2.6-Flash（`mimo-v2.6-flash`） | chat | 多模态标记对齐 MiMo-V2.5（vision / video / audio） |
| MiMo-V2.6-Pro（`mimo-v2.6-pro`） | chat | 对齐 MiMo-V2.5-Pro |

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

两个模型已标记 `deprecated: true`，请在下线前完成迁移。

### 模型参数约束

| 模型 | 行为 |
| --- | --- |
| `kimi-k2.7-code` | 网关仅接受 `temperature=1` 与 `top_p=0.95`；插件会覆盖其他取值 |
| `gpt-5.6-luna` | 上游拒绝 `temperature` 与 `top_p`；插件会剥离这两个参数 |

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
dify plugin package models/opencode-go -o dist/opencode_go-0.4.0.difypkg
```

## 链接

- OpenCode Go 文档：https://opencode.ai/docs/go/
- 模型列表 API：`https://opencode.ai/zen/go/v1/models`
- 认证 / API Key：https://opencode.ai/auth
- Dify 插件文档：https://docs.dify.ai/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## 免责声明

本插件为非官方社区插件，与 OpenCode / Anomaly 及 Dify 无隶属关系。
