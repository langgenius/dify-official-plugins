# Azure Blob Storage Datasource Plugin

Access Azure Blob Storage containers and blobs as a datasource for Dify with multiple authentication methods.

## Features

- **多认证方式**: 支持账户密钥、SAS 令牌、连接字符串、Azure AD OAuth
- **容器浏览**: 列出所有可访问的存储容器
- **Blob 管理**: 浏览、下载容器中的 Blob 文件
- **目录模拟**: 支持基于前缀的虚拟目录结构
- **大文件支持**: 自动分块下载大型 Blob 文件
- **多云支持**: 支持全球云、中国云、政府云、德国云
- **OAuth 完整支持**: 自动刷新访问令牌，无需重新授权
- **元数据丰富**: 提供完整的 Blob 属性和元数据

## Supported Authentication Methods

### 1. Account Key (推荐用于开发)
- 使用存储账户名称和访问密钥
- 提供完整的存储账户访问权限

### 2. SAS Token (推荐用于生产)
- 使用共享访问签名令牌
- 支持细粒度权限控制和时间限制
- 最小权限：读取和列表权限

### 3. Connection String
- 使用完整的连接字符串
- 包含所有必需的连接信息

### 4. Azure AD OAuth (推荐用于企业)
- 使用 Azure Active Directory 身份验证
- 支持自动刷新访问令牌
- 多云环境支持（全球云、中国云、政府云）
- 最小权限原则：仅需要 Storage 用户模拟权限

## Supported Content Types

- 所有类型的 Blob 文件
- 自动 MIME 类型检测
- 支持文本、图像、文档、压缩包等
- 大文件分块下载（>50MB）

## Azure Cloud Support

- **Global Azure**: core.windows.net (默认)
- **Azure China**: core.chinacloudapi.cn
- **Azure Government**: core.usgovcloudapi.net

## Version: 0.2.0

### Features in v0.2.0
- ✅ 账户密钥认证
- ✅ SAS 令牌认证  
- ✅ 连接字符串认证
- ✅ 容器和 Blob 浏览
- ✅ 大文件分块下载
- ✅ 多云环境支持
- ✅ 归档层检测和提示
- ✅ Azure AD OAuth 完整支持
- ✅ 自动刷新访问令牌

### Security Features
- 敏感凭证安全存储
- 权限验证和错误处理
- 最小权限原则
- 安全的认证流程
