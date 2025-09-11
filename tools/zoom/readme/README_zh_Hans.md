# Dify Zoom 插件

## 简介

该插件集成了 Zoom 视频会议平台，提供了全面的会议管理能力。它允许通过 Dify 平台自动创建、检索、更新和删除 Zoom 会议。该插件支持各种会议类型，包括即时会议、预定会议和重复会议，并提供高级配置选项。

## 安装

1. 在 [Zoom App Marketplace](https://marketplace.zoom.us/develop/create) 中创建您的应用程序。

   <img src="_assets/create_app.png" alt="Create App" width="300"/>

   *创建一个新的 Zoom 应用程序*

2. 选择 **General App** 作为应用程序类型。

3. 配置您的应用程序如下：
    - **App name**: Dify Zoom 插件
    - **Choose your app type**: Server-to-Server OAuth
    - **Would you like to publish this app on Zoom App Marketplace?**: No (for private use)

4. 在 **OAuth** 部分：
    - **OAuth Redirect URL**: 设置适当的重定向 URI：
        - 对于 SaaS (cloud.dify.ai) 用户：`https://cloud.dify.ai/console/api/oauth/plugin/langgenius/zoom/zoom/tool/callback`
        - 对于自托管用户：`http://<YOUR_LOCALHOST_CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/zoom/zoom/tool/callback`
    - **OAuth allow list**: 添加您的域名（如果需要）

5. 复制您的 **Client ID** 和 **Client Secret** 从应用程序凭据部分。

6. 选择 Scope 如下：

   <img src="_assets/add_scope.png" alt="Add Scope" width="300"/>

   *配置 OAuth 权限范围*

7. 添加测试用户：

   <img src="_assets/add_test_user.png" alt="Add Test User" width="300"/>

   *添加测试用户到您的应用程序*

8. 配置插件在 Dify：
    - 填写 **Client ID** 和 **Client Secret** 字段，值为您从 Zoom 应用程序中复制的值
    - 确保重定向 URI 与您在 Zoom App Marketplace 中配置的 URI 匹配
    - 点击 `Save and authorize` 以启动 OAuth 流程并授予权限

9. 完成 OAuth 授权过程，通过登录您的 Zoom 账户并批准应用程序权限。

## 使用演示

<img src="_assets/result.png" alt="Plugin Result" width="300"/>

*插件集成和使用演示*

## 工具描述

### zoom_create_meeting
创建一个新的 Zoom 会议，具有可定制的设置并获取会议链接。

**参数：**
- **topic** (string, 必填): 会议主题或标题
- **type** (select, 可选): 会议类型 - 即时 (1), 预定 (2), 重复无固定时间 (3), 或重复有固定时间 (8)。默认: 预定 (2)
- **start_time** (string, 可选): 会议开始时间（ISO 8601 格式，例如 2024-12-25T10:00:00Z）
- **duration** (number, 可选): 会议持续时间（分钟，1-1440）。默认: 60
- **password** (string, 可选): 可选密码以保护会议
- **waiting_room** (boolean, 可选): 启用等待室参与者。默认: true
- **join_before_host** (boolean, 可选): 允许参与者在主机到达前加入。默认: false
- **mute_upon_entry** (boolean, 可选): 自动静音参与者加入。默认: true
- **auto_recording** (select, 可选): 自动录制设置 - 无、本地或云。默认: 无
- **timezone** (string, 可选): 会议时区。默认: UTC
- **agenda** (string, 可选): 会议议程或详细描述

**返回：** 会议 ID、加入 URL、开始 URL、密码和会议详情。

### zoom_get_meeting
通过会议 ID 检索 Zoom 会议的详细信息。

**参数：**
- **meeting_id** (string, 必填): Zoom 会议的唯一标识符
- **occurrence_id** (string, 可选): 重复会议的 Occurrence ID
- **show_previous_occurrences** (boolean, 可选): 是否包含重复会议的先前发生。默认: false

**返回：** 完整的会议信息，包括设置、URL、主机详情和重复会议的发生数据。

### zoom_list_meetings
列出所有 Zoom 会议，支持高级过滤选项。

**参数：**
- **type** (select, 可选): 会议类型过滤 - 预定、实时、即将举行、即将举行的会议或之前的会议。默认: 预定
- **page_size** (number, 可选): 每页会议数量 (1-300)。默认: 30
- **page_number** (number, 可选): 要检索的页码 (从 1 开始)。默认: 1
- **from_date** (string, 可选): 过滤会议的开始日期 (YYYY-MM-DD 格式)
- **to_date** (string, 可选): 过滤会议的结束日期 (YYYY-MM-DD 格式)

**返回：** 会议列表，包括分页信息和应用的过滤器。

### zoom_update_meeting
更新现有的 Zoom 会议，具有新的设置和配置。

**参数：**
- **meeting_id** (string, 必填): 要更新的 Zoom 会议的唯一标识符
- **topic** (string, 可选): 新的会议主题或标题
- **type** (select, 可选): 新的会议类型
- **start_time** (string, 可选): 新的开始时间 (ISO 8601 格式)
- **duration** (number, 可选): 新的持续时间 (分钟，1-1440)
- **timezone** (string, 可选): 新的时区标识符
- **password** (string, 可选): 新的会议密码
- **agenda** (string, 可选): 新的会议议程或详细描述
- **waiting_room** (boolean, 可选): 更新等待室设置
- **join_before_host** (boolean, 可选): 更新加入主机设置
- **mute_upon_entry** (boolean, 可选): 更新加入时静音设置
- **auto_recording** (select, 可选): 新的自动录制设置
- **occurrence_id** (string, 可选): 更新特定发生的发生 ID

**返回：** 成功状态、更新后的会议信息和更改的详细信息。

### zoom_delete_meeting
删除 Zoom 会议，具有通知选项。

**参数：**
- **meeting_id** (string, 必填): 要删除的 Zoom 会议的唯一标识符
- **occurrence_id** (string, 可选): 删除特定发生的发生 ID
- **schedule_for_reminder** (boolean, 可选): 发送提醒电子邮件给注册者关于取消。默认: false
- **cancel_meeting_reminder** (boolean, 可选): 发送取消电子邮件给注册者和面板参与者。默认: false

**返回：** 成功状态、删除的会议信息和删除类型（整个会议或特定发生）。

## 隐私

请参阅 [隐私政策](PRIVACY.md) 以了解在使用此插件时如何处理您的数据。
