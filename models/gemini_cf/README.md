# Gemini（Cloudflare 代理）模型插件

本供应商通过 Cloudflare Worker 反向代理访问 Gemini v1beta API。安装后在 Dify 的“模型供应商”中配置以下两项：

- Base URL（必填）：形如 `https://<your-worker>.workers.dev`
- API Key（必填）：与你的 Worker 通信的密钥

请求约定：
- 路由与官方 Gemini 基本一致，例如：`{base_url}/v1beta/models/{model}:generateContent`
- 认证头：`x-api-key: <你的密钥>`

注意：
- 若你需要兼容 Dify 官方 `google_gemini` 供应商的认证（例如 `x-goog-api-key` 或 `?key=` 查询参数），请在 Worker 中做一层映射（例如将 `x-goog-api-key` 或 URL 的 `key` 参数转为 `x-api-key`）。
- 本插件内置了多款 2.5/2.0 的 LLM 型号。TTS 预览版如需支持，请另行补充 `tts` 类型的模型 YAML（或改造 Worker 与调用链）。
