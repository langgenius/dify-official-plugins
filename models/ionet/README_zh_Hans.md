# IO Intelligence（io.net）

[IO Intelligence](https://io.net)（io.net 出品）的 Dify 模型供应商插件。

IO Intelligence 提供 OpenAI 兼容的 **Chat Completions** API：
`https://api.intelligence.io.solutions/api/v1`（Bearer 认证；`GET /models` 公开可访问）。
模型 ID 为 `org/name` 形式，例如 `meta-llama/Llama-3.3-70B-Instruct`。

## 功能

- 预置 IO Intelligence 目录中的全部 35 个模型（GLM、DeepSeek、Kimi、Qwen、Llama、MiniMax、MiMo、Gemma、Mistral、gpt-oss），包含上下文窗口、工具/推理/视觉/视频能力，以及来自公开 `/models` 接口的逐模型定价
- 支持自定义模型（可输入新上线的模型 ID）
- 默认 API 地址：`https://api.intelligence.io.solutions/api/v1`

## 配置

1. 在 io.net 云控制台创建 API 密钥：https://cloud.io.net
2. 在 Dify 中安装本插件（Marketplace / 插件包 / debug 远程调试）。
3. 打开 **设置 → 模型供应商 → IO Intelligence**，粘贴 API 密钥并保存。
4. 在应用中选择 IO Intelligence 模型。

### 自定义模型

如果 io.net 在本插件更新前新增了模型：

1. 在 IO Intelligence 下添加自定义模型。
2. 模型名称 = [公开目录](https://api.intelligence.io.solutions/api/v1/models) 中的模型 ID（例如 `zai-org/GLM-5.3-Flash`）。
3. 可选：设置上下文长度 / 最大 Token / 函数调用 / 视觉。
