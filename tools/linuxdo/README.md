# LinuxDo Connect Plugin for Dify

**Author:** frederick  
**Version:** 0.0.1  
**Type:** Tool Plugin

## 概述 | Overview

LinuxDo Connect 插件允许你在 Dify 中直接连接和操作 LinuxDo 论坛。通过 LinuxDo Connect API，你可以进行身份验证、获取用户信息、搜索内容、获取个性化推荐，以及执行自动签到等操作。

The LinuxDo Connect plugin allows you to directly connect and interact with the LinuxDo forum within Dify. Through the LinuxDo Connect API, you can perform authentication, retrieve user information, search content, get personalized recommendations, and execute automatic check-ins.

## 功能特性 | Features

### 🔐 用户认证与信息获取 | User Authentication & Information
- 验证 API 密钥状态
- 获取详细用户信息（用户名、信任等级、活跃状态等）
- 支持快速验证模式

### 🔍 内容搜索 | Content Search
- 全站内容搜索（主题、帖子、分类）
- 高级过滤选项（分类筛选、结果排序）
- 支持按相关性、日期、浏览量、回复数排序
- 可自定义返回结果数量

## 安装配置 | Installation & Configuration

### 1. 获取 LinuxDo Connect API 凭据 | Get LinuxDo Connect API Credentials

访问 [LinuxDo Connect](https://connect.linux.do) 申请 API 访问权限：

1. **注册应用** | **Register Application**
   - 访问 https://connect.linux.do
   - 点击"我的应用接入" -> "申请新接入"
   - 填写应用信息和回调地址

2. **获取凭据** | **Get Credentials**
   - **Client ID**: 用于基础认证的客户端标识
   - **Client Secret**: 用于基础认证的客户端密钥  
   - **API Key**: 用于识别用户账户的 API 密钥

### 2. 在 Dify 中配置插件 | Configure Plugin in Dify

1. 在 Dify 中安装 LinuxDo Connect 插件
2. 在插件配置页面填入获取的凭据：
   - **Client ID**: 你的 LinuxDo Client ID
   - **Client Secret**: 你的 LinuxDo Client Secret
   - **API Key**: 你的 LinuxDo API Key

## 使用方法 | Usage

### 用户信息获取 | User Information

```python
# 获取完整用户信息
user_info = linuxdo_user_info(
    include_extra_info=True,
    verify_only=False
)

# 仅验证 API Key 状态（更快）
verification = linuxdo_user_info(
    include_extra_info=False,
    verify_only=True
)
```

### 内容搜索 | Content Search

```python
# 搜索所有内容
search_results = linuxdo_content_search(
    search_query="Python编程",
    search_type="all",
    limit=20,
    sort_by="relevance"
)

# 仅搜索主题
topic_results = linuxdo_content_search(
    search_query="机器学习",
    search_type="topics",
    category_filter="技术讨论",
    limit=10,
    sort_by="date"
)
```

## API 端点信息 | API Endpoints

### LinuxDo Connect API 端点
- **授权端点**: `https://connect.linux.do/oauth2/authorize`
- **Token 端点**: `https://connect.linux.do/oauth2/token`  
- **用户信息端点**: `https://connect.linux.do/api/user`
- **用户信息端点 (OAuth2)**: `https://connect.linux.do/oauth2/userinfo`

### 可获取的用户字段 | Available User Fields
| 字段 | 说明 | Field | Description |
|------|------|-------|-------------|
| `id` | 用户唯一标识（不可变） | `id` | Unique user identifier (immutable) |
| `username` | 论坛用户名 | `username` | Forum username |
| `name` | 论坛用户昵称（可变） | `name` | Forum display name (mutable) |
| `avatar_template` | 用户头像模板URL | `avatar_template` | User avatar template URL |
| `active` | 账号活跃状态 | `active` | Account active status |
| `trust_level` | 信任等级（0-4） | `trust_level` | Trust level (0-4) |
| `silenced` | 禁言状态 | `silenced` | Silenced status |
| `external_ids` | 外部ID关联信息 | `external_ids` | External ID associations |
| `api_key` | API访问密钥 | `api_key` | API access key |

## 数据结构 | Data Structures

### 用户信息响应 | User Info Response
```json
{
  "user_info": {
    "user_id": "string",
    "api_key_valid": true,
    "username": "string",
    "name": "string", 
    "trust_level": 0,
    "active": true,
    "admin": false,
    "moderator": false,
    "created_at": "2024-01-01T00:00:00Z",
    "last_seen_at": "2024-01-01T00:00:00Z"
  },
  "verification_result": {
    "status": "success",
    "user_id": "string",
    "api_key_valid": true,
    "message": "string"
  }
}
```

### 搜索结果响应 | Search Results Response
```json
{
  "search_results": [
    {
      "id": "string",
      "title": "string",
      "content": "string",
      "author": "string",
      "category": "string", 
      "url": "string",
      "created_at": "2024-01-01T00:00:00Z",
      "views": 0,
      "replies": 0,
      "relevance_score": 0.95
    }
  ],
  "search_summary": {
    "total_results": 0,
    "search_query": "string",
    "search_type": "string",
    "processing_time": 0.5,
    "filters_applied": ["string"]
  }
}
```

## 安全建议 | Security Recommendations

1. **保护凭据** | **Protect Credentials**
   - 妥善保管 Client Secret 和 API Key
   - 切勿在前端代码中暴露敏感信息
   - 定期更新 API 凭据

2. **网络安全** | **Network Security**  
   - 确保使用 HTTPS 协议传输数据
   - 验证所有用户输入数据

3. **访问控制** | **Access Control**
   - 基于用户信任等级实施服务限制
   - 监控 API 使用频率，防止滥用

## 故障排除 | Troubleshooting

### 常见问题 | Common Issues

**Q: API Key 验证失败**  
A: 请检查以下项目：
- 确认 API Key 格式正确
- 验证 Client ID 和 Client Secret 是否匹配
- 检查网络连接是否正常

**Q: 搜索结果为空**  
A: 可能的原因：
- 搜索关键词过于具体
- 分类筛选过于严格
- 尝试调整搜索参数或使用更通用的关键词

## 开发信息 | Development Information

### 依赖项 | Dependencies
- `dify_plugin>=0.2.0,<0.3.0`
- `requests>=2.31.0`

### 项目结构 | Project Structure
```
linuxdo/
├── manifest.yaml              # 插件清单文件
├── requirements.txt           # Python 依赖
├── main.py                   # 插件入口点
├── provider/
│   ├── linuxdo.py           # 提供者实现
│   └── linuxdo.yaml         # 提供者配置
├── tools/
│   ├── linuxdo.py           # 用户信息工具
│   ├── linuxdo.yaml         # 用户信息工具配置
│   ├── content_search.py    # 内容搜索工具
│   └── content_search.yaml  # 内容搜索工具配置
└── _assets/
    ├── icon.svg            # 插件图标
    └── icon-dark.svg       # 深色模式图标
```

## 许可证 | License

本插件遵循相应的开源许可证。使用前请确保遵守 LinuxDo 论坛的使用条款和 API 使用政策。

This plugin follows the corresponding open source license. Please ensure compliance with LinuxDo forum terms of use and API usage policies before use.

## 支持与反馈 | Support & Feedback

如有问题或建议，请通过以下方式联系：
- 创建 GitHub Issue
- 在 LinuxDo 论坛联系作者
- 发送邮件至开发者

For questions or suggestions, please contact us through:
- Create a GitHub Issue  
- Contact the author on LinuxDo forum
- Send email to the developer

---

**注意**: 使用本插件需要有效的 LinuxDo 账户和 Connect API 访问权限。请确保遵守论坛使用规则和 API 使用限制。

**Note**: Using this plugin requires a valid LinuxDo account and Connect API access permissions. Please ensure compliance with forum usage rules and API usage restrictions.

