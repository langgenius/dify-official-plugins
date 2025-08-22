# GitHub Datasource Plugin 使用指南

## 概述

GitHub 数据源插件允许您将 GitHub 仓库、Issues、Pull Requests 作为 Dify 的数据源。

## 认证方式

### 方式一：Personal Access Token（推荐）

1. 访问 [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. 点击 "Generate new token (classic)"
3. 选择以下权限：
   - `repo` - 访问私有和公共仓库
   - `user:email` - 获取用户邮箱
   - `read:user` - 读取用户信息
4. 生成并复制 token（格式：`ghp_xxxxxxxxxxxxxxxxxxxx`）
5. 在 Dify 中配置数据源时粘贴此 token

### 方式二：OAuth 应用

1. 访问 [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. 创建新的 OAuth App
3. 设置回调 URL：`https://your-dify-domain.com/console/api/oauth/callback`
4. 获取 Client ID 和 Client Secret
5. 在 Dify 中配置 OAuth 凭证

## 支持的内容类型

### 1. 仓库文件
- 代码文件（Python, JavaScript, etc.）
- 文档文件（Markdown, README）
- 配置文件（JSON, YAML）
- 其他文本文件

### 2. Issues
- Issue 标题和描述
- Issue 评论
- 标签和状态信息

### 3. Pull Requests
- PR 标题和描述
- PR 评论
- 分支信息

### 4. Wiki 页面
- Wiki 页面内容（计划支持）

## 使用步骤

1. **配置认证**：选择 Personal Access Token 或 OAuth 方式
2. **浏览仓库**：系统会列出您有权限访问的仓库
3. **选择内容**：选择要导入的文件、Issues 或 PR
4. **自动处理**：系统自动处理 Markdown 和其他格式

## 功能特性

### 自动内容处理
- Markdown 文件自动转换为 HTML
- 代码文件保持原格式
- 自动提取文件元数据

### 限流处理
- 自动检测 API 限流
- 智能重试机制
- 错误提示和等待建议

### 安全性
- 支持私有仓库访问
- 安全的 token 存储
- OAuth 标准流程

## 权限说明

### Personal Access Token 权限
- `repo`: 访问所有仓库（包括私有）
- `user:email`: 获取用户邮箱
- `read:user`: 读取基本用户信息

### OAuth 权限范围
- 仓库访问权限
- 用户信息读取权限
- Issues 和 PR 访问权限

## 常见问题

### Q: Token 无效怎么办？
A: 检查 token 是否正确复制，确保包含所需权限，token 未过期。

### Q: 遇到限流怎么办？
A: 系统会自动处理限流，请等待提示的时间后重试。

### Q: 无法访问私有仓库？
A: 确保 Personal Access Token 包含 `repo` 权限。

### Q: 支持哪些文件格式？
A: 支持所有文本格式，特别优化了 Markdown、JSON、YAML、代码文件等。

## 技术支持

如遇问题，请检查：
1. 网络连接是否正常
2. GitHub 服务状态
3. Token 权限是否足够
4. API 限流状态

## 版本信息

当前版本：v0.3.0
- ✅ Personal Access Token 认证
- ✅ OAuth 认证
- ✅ 仓库文件访问
- ✅ Issues 和 PR 支持
- ✅ 限流处理
- ✅ 内容自动处理

