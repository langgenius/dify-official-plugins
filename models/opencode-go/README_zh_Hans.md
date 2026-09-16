# OpenCode Go

[Dify](https://dify.ai) 的 [OpenCode Go](https://opencode.ai/docs/go/) 模型供应商插件。

OpenCode Go 是 $10/月 的订阅网关，提供精选开源编码模型。本插件通过 OpenAI 兼容的 Chat Completions API 将这些模型接入 Dify。

## 功能

- 预置 OpenCode Go 目录中的模型（GLM、Kimi、DeepSeek、MiMo、MiniMax、Qwen、LongCat、Hy）
- 支持自定义模型，便于接入官方新增的 model id
- 自动发送 OpenCode 要求的请求头：
  - `User-Agent`（标识客户端，默认 `dify-opencode-go-plugin/0.1.0`）
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
3. 可按需设置上下文长度、最大 token、Function Calling、视觉能力。

## 协议说明

本插件使用 OpenAI 兼容路径（`{base}/chat/completions`）。

本地对真实 OpenCode Go Key 的冒烟结果（2026-09-10）：

| 模型 | 状态 |
| --- | --- |
| glm-5.3-flash / glm-5.x | OK（stream + non-stream） |
| mimo-v2.5 | OK |
| kimi-k2.6 | OK |
| deepseek-v4-flash | OK |
| qwen3.8-flash / qwen3.7-plus | OK |
| hy3 | OK |
| minimax-m3 | OK |
| minimax-m2.7 | 网关 500（可能是临时问题） |
| grok-4.6 / gpt-5.6-luna | 不支持 `oa-compat`（仅 Responses API） |
| muse-spark-* | 区域限制 / 仅 Responses |

Grok / GPT 5.6 Luna / Muse Spark **未**列为预置模型，因为 OpenCode Go 在 Chat Completions 端点会拒绝它们。

## 本地调试

```bash
pip install "dify_plugin>=0.10.0"
```

复制 `.env.example` 为 `.env`，填入 Dify 插件调试页中的密钥。

```bash
python -m main
```

本地单元测试（不访问网络）：

```bash
python test_session_id.py
python test_session_runtime.py
python test_extra_headers.py
python test_backward_compat_002.py
```

打包：

```bash
dify plugin package models/opencode-go -o dist/opencode_go-0.1.0.difypkg
```

## 相关链接

- OpenCode Go 文档：https://opencode.ai/docs/go/
- 模型列表 API：`https://opencode.ai/zen/go/v1/models`
- API Key：https://opencode.ai/auth
- Dify 插件开发文档：https://docs.dify.ai/zh/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## 免责声明

本插件为社区非官方实现，与 OpenCode / Anomaly 及 Dify 无官方关联。
