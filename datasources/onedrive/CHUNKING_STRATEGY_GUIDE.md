# OneDrive文档分块策略指南

## 🎯 **Pipeline节点选择建议**

基于您的需求实现general chunker或Parent-Child chunk功能，推荐以下节点配置：

### 推荐方案：使用"文档提取器"节点

## 📋 **Pipeline配置流程**

### 1. **添加文档提取器节点**
```
Pipeline操作:
1. 点击 "+" 添加节点
2. 选择 "转换" → "文档提取器"
3. 设置节点名称: doc_chunker
```

### 2. **配置文档提取器参数**
```yaml
节点配置:
  节点名称: doc_chunker
  输入源: {{onedrive.result}}
  
  分块策略:
    ✅ 智能分块: 启用
    分块大小: 1000 字符
    重叠长度: 100 字符
    分块方式: 
      - 语义分块 (推荐)
      - 固定长度分块
      - 段落分块
    
  高级选项:
    ✅ 保持文档结构
    ✅ 提取元数据
    ✅ 生成分块ID
```

### 3. **Parent-Child分块实现**
```yaml
# 如果文档提取器支持层级分块
层级分块配置:
  Parent块大小: 3000 字符  # 大块作为上下文
  Child块大小: 1000 字符   # 小块用于检索
  重叠策略: 保持Parent-Child关联
  
输出结构:
  chunks: [
    {
      "content": "子块内容",
      "parent_id": "父块ID", 
      "chunk_id": "唯一标识",
      "metadata": {...}
    }
  ]
```

## 🔄 **替代方案：代码执行节点**

如果文档提取器不满足需求，使用代码执行节点：

### 自定义分块脚本
```python
import re
from typing import List, Dict

def advanced_chunker(document: str, parent_size: int = 3000, child_size: int = 1000, overlap: int = 100) -> Dict:
    """
    实现Parent-Child分块策略
    """
    
    # 1. 创建Parent chunks
    parent_chunks = []
    start = 0
    parent_id = 0
    
    while start < len(document):
        end = min(start + parent_size, len(document))
        
        # 寻找合适的分割点(句号、段落等)
        if end < len(document):
            for i in range(end, max(end - 200, start), -1):
                if document[i] in '.!?\n':
                    end = i + 1
                    break
        
        parent_chunk = {
            "id": f"parent_{parent_id}",
            "content": document[start:end],
            "start_pos": start,
            "end_pos": end
        }
        parent_chunks.append(parent_chunk)
        
        start = end - overlap
        parent_id += 1
    
    # 2. 为每个Parent chunk创建Child chunks
    all_child_chunks = []
    
    for parent in parent_chunks:
        child_chunks = create_child_chunks(
            parent["content"], 
            parent["id"], 
            child_size, 
            overlap
        )
        all_child_chunks.extend(child_chunks)
    
    return {
        "parent_chunks": parent_chunks,
        "child_chunks": all_child_chunks,
        "total_parents": len(parent_chunks),
        "total_children": len(all_child_chunks)
    }

def create_child_chunks(parent_content: str, parent_id: str, child_size: int, overlap: int) -> List[Dict]:
    """
    从父块创建子块
    """
    child_chunks = []
    start = 0
    child_id = 0
    
    while start < len(parent_content):
        end = min(start + child_size, len(parent_content))
        
        # 寻找合适的分割点
        if end < len(parent_content):
            for i in range(end, max(end - 100, start), -1):
                if parent_content[i] in '.!?\n ':
                    end = i + 1
                    break
        
        child_chunk = {
            "id": f"{parent_id}_child_{child_id}",
            "parent_id": parent_id,
            "content": parent_content[start:end],
            "position_in_parent": child_id
        }
        child_chunks.append(child_chunk)
        
        start = end - overlap
        child_id += 1
    
    return child_chunks

# 主要执行逻辑
def main():
    # 获取输入文档
    input_data = {{onedrive.result}}
    document_content = input_data.get("content", "")
    
    # 执行分块
    chunked_result = advanced_chunker(
        document_content,
        parent_size=3000,
        child_size=1000, 
        overlap=100
    )
    
    # 返回结果
    return {
        "chunked_documents": chunked_result["child_chunks"],
        "parent_documents": chunked_result["parent_chunks"],
        "chunk_metadata": {
            "strategy": "parent-child",
            "total_chunks": chunked_result["total_children"],
            "total_parents": chunked_result["total_parents"]
        }
    }

# 执行
result = main()
```

## 🎮 **实际Pipeline配置**

### 完整数据流设计:
```
[OneDrive数据源] → [文档提取器] → [知识库/向量存储]
       ↓              ↓                ↓
    文件内容     →  分块文档数组    →   向量化存储
```

### 节点配置详情:
```yaml
1. OneDrive数据源:
   - 输出: {{onedrive.result}}
   
2. 文档提取器:
   - 输入: {{onedrive.result}}
   - 输出: {{doc_chunker.chunks}}
   
3. 知识库:
   - 输入: {{doc_chunker.chunks}}
   - 存储: 向量数据库
```

## 💡 **分块策略选择建议**

### 根据文档类型选择策略:

**技术文档/API文档:**
```yaml
分块策略: 语义分块
Parent大小: 2000-3000字符
Child大小: 800-1200字符
重叠: 10-15%
```

**长篇文档/书籍:**
```yaml
分块策略: 章节分块 + Parent-Child
Parent大小: 5000字符 (整个章节)
Child大小: 1000字符 (段落级)
重叠: 100字符
```

**结构化文档:**
```yaml
分块策略: 结构感知分块
按标题层级: H1 → Parent, H2/H3 → Child
保持层级关系: 是
包含上下文: 是
```

## ⚙️ **高级配置选项**

### 元数据增强:
```yaml
分块元数据包含:
  - chunk_id: 唯一标识
  - parent_id: 父块引用
  - position: 在文档中的位置
  - source_file: 来源文件信息
  - semantic_type: 语义类型(标题/正文/列表等)
  - relationships: 与其他块的关系
```

### 质量控制:
```yaml
分块质量检查:
  - 最小块大小: 200字符
  - 最大块大小: 2000字符
  - 避免孤立句子: 是
  - 保持完整段落: 优先
  - 去重处理: 启用
```

## 🚀 **推荐实施步骤**

1. **首选**: 使用"文档提取器"节点的内置分块功能
2. **备选**: 如果功能不足，使用"代码执行"节点实现自定义逻辑
3. **测试**: 小规模测试不同分块策略的效果
4. **优化**: 根据检索效果调整参数
5. **扩展**: 根据需要添加更多文档处理功能

这样您就能在Dify Pipeline中实现高效的文档分块处理了！
