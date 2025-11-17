# Dify 的 Airtable Trigger 插件

## 概述

此插件使 Dify 能够在您的 base 中的记录被创建、更新或删除时从 Airtable 接收实时 Webhook 通知。它提供了 Airtable 与 Dify 工作流之间的无缝集成。

## 获取 Airtable Personal Access Token

![1](./_assets/1.png)
1. 前往 [Airtable Account Settings](https://airtable.com/create/tokens)
2. 点击"Create new token"
3. 为您的令牌命名（例如，"Dify Integration"）
4. 添加以下范围:
   - `webhook:manage`
   - `data.records:read`
   - `schema.bases:read`
5. 添加对要监控的特定 base 的访问权限
6. 点击"Create token"并复制令牌值

## 配置

### 设置项

- **Personal Access Token**: 您的 Airtable Personal Access Token
- **Base ID**: 要监控的 Airtable base 的 ID（在 base URL 中找到: `https://airtable.com/{baseId}/...`）
- **Events**: 选择要监控的事件类型（创建、更新、删除）
- **Table IDs**: 要监控的特定表 ID 的逗号分隔列表（留空以监控所有表）

## 使用示例

1. 在您的 Dify 工作区中安装 Airtable Trigger 插件
2. 创建新工作流并添加 Airtable Trigger
3. 使用您的 Personal Access Token 和 Base ID 配置触发器
4. 选择要监控的事件
5. 添加任何可选过滤器以缩小通知范围
6. 保存并激活您的工作流

## 输出变量

触发器为您的工作流提供以下变量：

```json
{
  "base_id": "appXXXXXXXXXXXXXX",
  "webhook_id": "achXXXXXXXXXXXXXX",
  "timestamp": "2023-01-01T00:00:00.000Z",
  "cursor": 9,
  "payloads": { /* 完整的 Webhook 通知负载 */ }
}
```

## 参考资料

- [Airtable Webhooks API 文档](https://airtable.com/developers/web/api/webhooks-overview)
- [Airtable 认证](https://airtable.com/developers/web/api/authentication)
- [Airtable 范围](https://airtable.com/developers/web/api/scopes)
