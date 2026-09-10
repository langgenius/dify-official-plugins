# OpenCode Go 模型供应商插件

## 目录结构

```
.
├── main.py
├── manifest.yaml
├── pyproject.toml
├── icon.svg
├── provider/
│   ├── opencode_go.yaml
│   └── opencode_go.py
└── models/
    └── llm/
        ├── llm.py
        ├── _position.yaml
        └── <model-id>.yaml
```

## 实现要点

1. 继承 `OAICompatLargeLanguageModel`，走 OpenAI Chat Completions。
2. 默认 `endpoint_url = https://opencode.ai/zen/go/v1`。
3. 请求头：
   - `User-Agent: dify-opencode-go-plugin/0.1.0`
   - `x-opencode-session: <user or uuid>`
4. 供应商凭证校验默认调用 `glm-5.3-flash`。

## 调试

1. Dify → 插件 → 调试插件，复制 Host + Key。
2. 写入 `.env`：
   ```
   INSTALL_METHOD=remote
   REMOTE_INSTALL_HOST=<host>
   REMOTE_INSTALL_PORT=5003
   REMOTE_INSTALL_KEY=<key>
   ```
3. `python -m main`

## 打包

```bash
dify plugin package .
```
