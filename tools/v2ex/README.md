# V2EX Content Search Plugin

[中文](#中文) | [English](#english)

## 中文

### 描述

V2EX内容搜索插件是一个用于Dify的工具插件，允许用户搜索和获取V2EX论坛的各种内容，包括热门主题、最新主题、节点信息和用户资料。

### 功能特性

- 🔥 **热门主题搜索**: 获取V2EX当前热门讨论话题
- 📰 **最新主题搜索**: 获取最新发布的主题内容
- 🏷️ **节点信息查询**: 查看特定节点的详细信息
- 👤 **用户资料查询**: 获取用户的详细资料信息
- 🌐 **多语言支持**: 支持中文、英文、日文、葡萄牙文
- ⚡ **高效检索**: 自定义结果数量限制，快速获取所需信息

### 安装要求

- Python 3.12+
- Dify平台

### 使用方法

1. 在Dify中安装此插件
2. 选择搜索类型（热门主题/最新主题/节点信息/用户信息）
3. 根据需要输入搜索关键词：
   - 节点信息: 输入节点名称
   - 用户信息: 输入用户名或用户ID
   - 热门/最新主题: 可留空获取默认结果
4. 设置结果数量限制（1-50，默认10）

### 参数说明

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| search_type | 选择 | 是 | 搜索类型（hot_topics/latest_topics/node_info/user_info） |
| search_query | 字符串 | 否 | 搜索关键词 |
| limit | 数字 | 否 | 结果数量限制（默认10，最大50） |

### 版本信息

- **作者**: frederick
- **版本**: 0.0.1
- **类型**: 工具插件
- **架构支持**: amd64, arm64

---

## English

### Description

The V2EX Content Search Plugin is a tool plugin for Dify that allows users to search and retrieve various types of content from the V2EX forum, including hot topics, latest topics, node information, and user profiles.

### Features

- 🔥 **Hot Topics Search**: Retrieve currently trending discussion topics from V2EX
- 📰 **Latest Topics Search**: Get the most recently published topics
- 🏷️ **Node Information Query**: View detailed information about specific nodes
- 👤 **User Profile Query**: Retrieve detailed user profile information
- 🌐 **Multi-language Support**: Supports Chinese, English, Japanese, and Portuguese
- ⚡ **Efficient Retrieval**: Customizable result limits for fast information access

### Requirements

- Python 3.12+
- Dify Platform

### Usage

1. Install this plugin in Dify
2. Select the search type (Hot Topics/Latest Topics/Node Info/User Info)
3. Enter search keywords as needed:
   - Node Info: Enter node name
   - User Info: Enter username or user ID  
   - Hot/Latest Topics: Can be left empty for default results
4. Set result limit (1-50, default 10)

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| search_type | Select | Yes | Search type (hot_topics/latest_topics/node_info/user_info) |
| search_query | String | No | Search keywords |
| limit | Number | No | Result limit (default 10, max 50) |

### Version Information

- **Author**: frederick
- **Version**: 0.0.1
- **Type**: Tool Plugin
- **Architecture Support**: amd64, arm64

### Privacy

This plugin respects user privacy and follows V2EX's terms of service. Please refer to [PRIVACY.md](PRIVACY.md) for detailed privacy information.

### License

Please refer to the project's license terms for usage rights and restrictions.

