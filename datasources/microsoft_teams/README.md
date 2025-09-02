# Microsoft Teams Datasource Plugin

Access Microsoft Teams data including teams, channels, messages, chats, and files as a datasource for Dify.

## Features

- **团队访问**: 浏览用户加入的所有团队
- **频道支持**: 访问团队中的标准频道和私有频道
- **消息获取**: 获取频道消息和回复内容
- **聊天集成**: 支持一对一聊天和群组聊天 (v1.1.0)
- **文件访问**: 获取频道和聊天中的文件附件 (v1.1.0)
- **OAuth认证**: 使用 Microsoft Azure AD OAuth 2.0 安全认证
- **自动刷新**: 自动处理访问令牌刷新和错误重试

## Supported Content Types

- 团队信息和成员列表
- 频道详情和消息历史
- 一对一和群组聊天
- 消息附件和文件
- @提及和回复内容
- 会议记录（通过聊天消息）

## Required Permissions

- `Team.ReadBasic.All` - 读取团队基本信息
- `Channel.ReadBasic.All` - 读取频道基本信息
- `ChannelMessage.Read.All` - 读取频道消息
- `Chat.Read` - 读取聊天消息
- `Files.Read.All` - 读取文件
- `User.Read` - 读取用户信息

## Version: 1.1.0

### What's New in v1.1.0
- ✅ 聊天消息支持（一对一和群聊）
- ✅ 文件附件访问
- ✅ 改进的错误处理和令牌刷新
- ✅ 优化的内容解析和格式化

### v1.0.0 Features
- ✅ 团队和频道浏览
- ✅ 频道消息获取
- ✅ OAuth 2.0 认证
- ✅ 基础错误处理



