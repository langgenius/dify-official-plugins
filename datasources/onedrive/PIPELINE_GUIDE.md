# OneDrive数据源Pipeline接入指南

## 🎯 **核心概念**

OneDrive数据源在Pipeline中有两个主要功能：
1. **文件浏览**：获取文件列表，供用户选择
2. **文件下载**：获取具体文件内容，供后续处理

## 📊 **数据类型详解**

### OnlineDriveFile 结构
```python
{
    "id": "4C588C50361D50A3!857",    # OneDrive文件唯一标识
    "name": "document.pdf",          # 文件名
    "size": 2048576,                 # 文件大小（字节）
    "type": "file"                   # 类型：file 或 folder
}
```

### 文件内容消息结构
```python
{
    "content": b"PDF文件的二进制内容...",  # 实际文件字节数据
    "meta": {
        "file_name": "document.pdf",     # 原文件名
        "mime_type": "application/pdf"   # MIME类型
    }
}
```

## 🔧 **Pipeline中的配置方式**

### 方式1：直接文件处理
```yaml
节点配置:
  OneDrive数据源:
    - 节点名称: onedrive_files
    - 操作类型: 下载文件
    - 文件ID: 4C588C50361D50A3!857
    
  文档加载器:
    - 输入: {{onedrive_files.result}}
    - 文本提取: 启用
    - 分块大小: 1000
    
  知识库:
    - 文档源: {{文档加载器.documents}}
```

### 方式2：条件处理
```yaml
节点配置:
  OneDrive数据源:
    - 节点名称: onedrive_source
    
  条件判断:
    - 条件: {{onedrive_source.result.type}} == "file"
    - 真分支: 处理文件
    - 假分支: 处理文件夹
    
  文件处理器:
    - 输入: {{onedrive_source.result}}
```

## 🎮 **Dify界面操作步骤**

### 步骤1：添加OneDrive数据源节点
1. 在Pipeline编辑器中点击"+"
2. 选择"数据源" → "OneDrive"
3. 配置认证信息（如果还没有）

### 步骤2：配置数据源参数
```
节点设置:
├── 节点名称: onedrive_docs (可自定义)
├── 操作模式: 下载文件
└── 文件选择: 
    ├── 文件ID: 4C588C50361D50A3!857
    └── 或者浏览选择文件
```

### 步骤3：连接后续节点
```
Pipeline流程:
[OneDrive] → [文档处理] → [知识库]
     ↓           ↓           ↓
变量: result → documents → 存储
```

### 步骤4：变量映射
```javascript
// 在后续节点中使用
文档处理器输入: {{onedrive_docs.result}}
知识库文档源: {{文档处理器.documents}}
```

## 🔍 **变量引用语法**

### 基本语法
```javascript
// 完整结果
{{节点名称.result}}

// 文件信息 
{{节点名称.result.file_info.id}}
{{节点名称.result.file_info.name}}

// 数据源类型
{{节点名称.result.datasource_type}}
```

### 实际示例
```javascript
// 如果OneDrive节点名为 "onedrive_files"
{{onedrive_files.result}}                    # 完整文件数据
{{onedrive_files.result.file_info.id}}       # 文件ID
{{onedrive_files.result.datasource_type}}    # "online_drive"
```

## ⚙️ **高级用法**

### 批量文件处理
```yaml
OneDrive浏览:
  - 获取文件夹列表
  
循环处理:
  - 遍历: {{onedrive_browse.result.files}}
  - 对每个文件: {{item.id}}
  
文件下载:
  - 文件ID: {{循环项.id}}
```

### 文件类型过滤
```yaml
条件节点:
  - 条件: {{onedrive.result.file_info.name}} ends with ".pdf"
  - 真分支: PDF处理流程
  - 假分支: 其他格式处理
```

## 📋 **常见配置错误**

### 1. 变量名错误
```javascript
❌ 错误: {{OneDrive.result}}     // 大小写错误
✅ 正确: {{onedrive.result}}     // 使用实际节点名称
```

### 2. 嵌套访问错误
```javascript
❌ 错误: {{onedrive.file_info.id}}        // 缺少result层级
✅ 正确: {{onedrive.result.file_info.id}} // 完整路径
```

### 3. 节点连接错误
```
❌ 错误: OneDrive → 知识库 (直接连接)
✅ 正确: OneDrive → 文档处理器 → 知识库 (需要中间处理)
```

## 🧪 **调试技巧**

### 1. 使用调试模式
- 在Pipeline中启用调试模式
- 查看每个节点的输出值
- 确认变量格式正确

### 2. 检查输出格式
```javascript
console.log({{onedrive.result}});  // 查看完整输出结构
```

### 3. 分步测试
- 先测试OneDrive连接
- 再测试文件下载
- 最后测试完整流程

## 💡 **最佳实践**

1. **节点命名**：使用有意义的名称，如`onedrive_docs`、`onedrive_images`
2. **错误处理**：添加条件节点检查文件是否存在
3. **类型检查**：验证文件类型再处理
4. **权限管理**：确保OneDrive权限足够
5. **缓存考虑**：大文件处理时考虑缓存策略

这样，您就可以在Dify Pipeline中有效使用OneDrive数据源了！
