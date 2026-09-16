# OpenCode Go

[Dify](https://dify.ai) 的 [OpenCode Go](https://opencode.ai/docs/go/) 模型供应商插件。

OpenCode Go 是 $10/月 的订阅网关，提供精选开源编码模型。本插件将这些模型以单一供应商形式接入 Dify。

## 功能

- 预置 OpenCode Go 目录中的模型（GLM、Kimi、DeepSeek、MiMo、MiniMax、Qwen、LongCat、Hy、Grok、GPT Luna、Muse Spark、Union Alpha）
- 自定义模型支持，并提供 **API 协议** 选择（`chat` / `anthropic` / `responses`）
- 同一供应商内完整支持三类上游协议：
  - **Chat Completions**（`{base}/chat/completions` + `Authorization: Bearer`）— 多数模型默认
  - **Anthropic Messages**（`{base}/messages` + `x-api-key`）— 仅 `/messages` 可用的模型（如 `union-alpha`）
  - **OpenAI Responses**（`{base}/responses` + `Authorization: Bearer`）— 仅 `/responses` 可用的模型（如 `grok-4.6`、`gpt-5.6-luna`、`muse-spark-*`）
- **三条协议路径都会**发送 OpenCode 必需请求头：
  - `User-Agent`（默认 `dify-opencode-go-plugin/0.2.0`）
  - `x-opencode-session`（会话路由 / prompt cache）
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
2. 模型名称填写 [Go 文档](https://opencode.ai/docs/go/) 中的 model id（例如 `kimi-k2.6`）。
3. 设置 **API 协议** 与模型端点一致：
   - `chat`（默认）→ `/chat/completions`
   - `anthropic` → `/messages`（`union-alpha` 等仅 Messages 可用的模型）
   - `responses` → `/responses`（`grok-4.6`、`gpt-5.6-luna`、`muse-spark-*`）
4. 可按需设置上下文长度、最大 token、Function Calling、视觉能力。

## 协议矩阵

| 协议 | 端点 | 认证 | Session | UA |
| --- | --- | --- | --- | --- |
| chat | `{base}/chat/completions` | `Authorization: Bearer` | 必须 | 必须 |
| anthropic | `{base}/messages` | `x-api-key` + `anthropic-version: 2023-06-01` | 必须 | 必须 |
| responses | `{base}/responses` | `Authorization: Bearer` | 必须 | 必须 |

### 0.2.0 新增预置模型

| 模型 | 协议 | 说明 |
| --- | --- | --- |
| Union Alpha Free（`union-alpha`） | anthropic | 免费 / 限时；走 oa-compat `/chat/completions` 会 500 |
| Grok 4.6（`grok-4.6`） | responses | 文档标明仅 Responses |
| GPT 5.6 Luna（`gpt-5.6-luna`） | responses | 文档标明仅 Responses；**部分地区受限** |
| Muse Spark 1.3 Contributor | responses | **区域限制**（Meta 地理政策）；Contributor 档可能用于训练 |
| Muse Spark 1.2 Contributor | responses | 同上 |

Qwen / MiniMax 继续走 Chat Completions（oa-compat）。OpenCode 文档虽列出 `/messages`，但 oa-compat 实测 200，保持可避免回归。

本地实测矩阵（2026-09-16，0.2.0）：

| 模型 | 状态 |
| --- | --- |
| glm-5.3-flash 等 chat 模型 | OK（流式 + 非流式） |
| union-alpha 经 anthropic `/messages` | OK（流式 + 非流式） |
| union-alpha 经 chat `/chat/completions` | 500（预期失败） |
| grok-4.6 经 responses `/responses` | OK（流式 + 非流式） |
| gpt-5.6-luna 经 responses | **区域受限**（`unsupported_country_region_territory`） |
| muse-spark-* | 区域限制，视网络环境而定 |

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
```

在线冒烟（需 `OPENCODE_GO_API_KEY`）：

```bash
python test_smoke_live.py
```

打包：

```bash
dify plugin package models/opencode-go -o dist/opencode_go-0.2.0.difypkg
```

## 链接

- OpenCode Go 文档：https://opencode.ai/docs/go/
- 模型列表 API：`https://opencode.ai/zen/go/v1/models`
- 认证 / API Key：https://opencode.ai/auth
- Dify 插件文档：https://docs.dify.ai/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## 免责声明

本插件为非官方社区插件，与 OpenCode / Anomaly 及 Dify 无隶属关系。
