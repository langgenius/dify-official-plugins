# Typeform Trigger 插件

Dify 触发器插件，监听 Typeform `form_response` Webhook。每个提交都将连同完整的响应负载一起转发到您的工作流，以便您可以实时自动化后续操作。

## 快速开始

1. 在您的 Dify 工作区中安装插件并将触发器拖入工作流。
2. 选择要连接的方式（手动 Webhook、Personal Access Token 或 OAuth）。
3. 选择要监听的 Typeform（API Key / OAuth 模式必需，手动时为可选过滤器）。
4. 保存工作流并在 Typeform 中提交测试响应以确认事件到达 Dify。

## 连接模式

### 手动 Webhook（复制和粘贴）

1. 打开您的 Typeform 表单 → **Connect** → **Webhooks**。
2. 使用 Dify 端点添加新 Webhook（将此触发器添加到工作流时显示）。
3. （推荐）启用"Secret"并粘贴任何随机字符串。在触发器订阅的 *Webhook Secret* 字段中记录相同的值，以便插件可以验证签名。
4. 启用 Webhook 并提交测试响应以确认您收到 `2xx`。

> 如果您通过 Typeform API 管理 Webhook，请在创建或更新 Webhook 时设置 `secret` 字段。在 Dify 内使用相同的值。

### 通过 Personal Access Token 自动管理 Webhook

1. 在 Dify 中，配置触发器时选择 **Connect with API Key**。
2. 生成具有 `forms:read`、`webhooks:read` 和 `webhooks:write` 范围的 Typeform Personal Access Token（Account → Personal tokens）。
3. 将令牌粘贴到触发器配置中。Dify 将获取您的表单并显示动态下拉列表。
4. 选择要订阅的表单。您可以选择覆盖生成的 Webhook 密钥。
5. Dify 在 Typeform 中创建（或更新）Webhook 并存储密钥以进行签名验证。

### 通过 OAuth 2.0 自动管理 Webhook

1. 在 [Typeform Developer Portal](https://developer.typeform.com/my-apps) 中创建应用程序并启用 `forms:read`、`webhooks:read`、`webhooks:write` 和 `offline` 范围。
2. 在触发器配置中输入应用的 client ID 和 client secret，然后点击 **Connect with OAuth**。
3. 完成 Typeform 同意流程。Dify 交换代码以获取令牌（并保留刷新令牌，以便可以更新过期的访问令牌）。
4. 从动态下拉列表中选择目标表单，并可选择覆盖生成的密钥。
5. Dify 使用您的 OAuth 凭据在 Typeform 中配置 Webhook。

### 订阅参数

| 参数 | 使用时 | 描述 |
|-----------|-----------|-------------|
| `form_id` | 始终可选 | 当您手动管理 Webhook 时过滤到单个表单。在 API Key / OAuth 模式下，此字段变为动态下拉列表并且是必需的。 |
| `webhook_secret` | 始终可选 | 当您手动配置 Webhook 时，用于验证 `Typeform-Signature` 标头的共享密钥。 |
| `webhook_secret` 覆盖 | API Key & OAuth | 允许您在 Dify 为您创建 Webhook 时提供自定义密钥，而不是让 Dify 生成一个。 |

当 Dify 代表您创建 Webhook 时，它会将生成的（或覆盖的）密钥存储在订阅中，以便签名验证自动工作。

### 事件参数

- `hidden_field_filter`: 与 `form_response.hidden` 匹配的逗号分隔 `key=value` 对。
- `variable_filter`: 与 `form_response.variables` 中的条目匹配的逗号分隔 `key=value` 对。

如果任何过滤器失败，事件将被忽略，因此您的工作流不会触发。

## 支持的事件

- `form_response_received` — 为每个 Typeform Webhook 传递触发（`event_type = "form_response"`）。

### 负载形状

事件输出模式保证：

```json
{
  "event_id": "LtWXD3crgy",
  "event_type": "form_response",
  "form_response": {
    "form_id": "lT4Z3j",
    "token": "a3a12ec67a1365927098a606107fac15",
    "...": "..."
  }
}
```

Typeform 提供的所有其他字段（答案、定义、变量、隐藏字段等）都保留以供下游使用。

## 故障排除

- **OAuth 登录失败**: 确认重定向 URI 与 Dify 中显示的匹配，并且 Typeform 应用授予 `forms:read`、`webhooks:read`、`webhooks:write` 和 `offline`。
- **表单下拉列表为空**: 访问令牌必须包括 `forms:read`；重新生成 Personal Access Token 或通过 OAuth 重新授权。
- **工作流从不触发**: 确保 Typeform Webhook 显示"Enabled"，触发器在 Dify 中处于活动状态，并且在两侧配置了相同的 Webhook 密钥。
- **签名验证错误**: 在 Typeform 中轮换 Webhook 密钥并将新值粘贴到 Dify 中（手动模式）或重新连接，以便 Dify 可以重新生成它（API Key / OAuth）。

## 参考资料

- [Typeform Webhooks API 文档](https://www.typeform.com/developers/webhooks/)
- [Typeform Webhook 安全指南](https://www.typeform.com/developers/webhooks/secure-your-webhooks/)
- [Typeform Personal Access Tokens](https://admin.typeform.com/account#/section/tokens)
- [Typeform OAuth 范围](https://www.typeform.com/developers/webhooks/secure-your-webhooks/#oauth-scopes)
