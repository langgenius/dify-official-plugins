# Airtable 触发器

一个 Dify 插件，当 Airtable base 中的记录被创建、更新或删除时，提供实时 webhook 通知。

## 功能特性

- 记录变化的实时通知
- 支持创建、更新和删除事件
- 灵活的表格、字段和关键词过滤
- 安全的 HMAC 签名验证
- 自动刷新 webhook（处理 7 天过期）

## 快速开始

1. 获取你的 Airtable 个人访问令牌，需要以下权限：
   - `webhook:manage`
   - `data.records:read`
   - `schema.bases:read`

2. 从 Airtable base URL 中找到你的 Base ID

3. 使用你的令牌和 base ID 配置插件

4. 选择要监控的事件并添加过滤器

详细文档请参阅 [README.md](./README.md)
