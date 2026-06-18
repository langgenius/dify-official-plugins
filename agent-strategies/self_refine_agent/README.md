# Self-Refine Agent Strategy

**自我优化 Agent 策略插件 for Dify**

## 概述

Self-Refine Agent Strategy 是一个基于 [Self-Refine (NeurIPS 2023)](https://arxiv.org/abs/2303.17651) 论文实现的 Dify Agent 策略插件。它通过自动批判和迭代优化机制，提升 Agent 输出质量。

## 核心特性

- **自动评估**：LLM 作为评判器，自动评估输出质量
- **智能批判**：识别输出中的具体问题和改进点
- **迭代优化**：将批判意见注入下一轮执行，持续改进
- **透明流程**：所有中间步骤（执行、评估、批判）均可见
- **可配置参数**：支持自定义最大迭代次数和优化次数

## 工作流程

```
1. Execute (执行) → 运行 Agent 任务
2. Evaluate (评估) → 检查输出是否满意
3. Critique (批判) → 生成具体改进建议
4. Refine (优化) → 将批判注入上下文重新执行
5. Repeat (重复) → 直到达到质量阈值或最大次数
```

## 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | model-selector | - | 使用的 LLM 模型 |
| `tools` | array[tools] | - | 可用工具列表 |
| `instruction` | string | - | 系统指令 |
| `query` | string | - | 用户查询 |
| `context` | array[object] | - | 上下文信息（可选）|
| `maximum_iterations` | number | 5 | Agent 单次执行的最大迭代次数 |
| `max_refinements` | number | 2 | 最大优化次数（0-5）|

## 当前状态

**Phase 3: 完整实现 ✅**
- ✅ 完整的目录结构
- ✅ manifest.yaml 配置
- ✅ provider 和 strategy 框架
- ✅ 完整的自我优化循环逻辑
- ✅ LLM 调用和工具执行
- ✅ 评估和批判机制
- ✅ 流式输出和日志
- ✅ 错误处理和 fallback

## 安装和调试

### 本地远程调试

1. 配置 `.env` 文件：
```bash
INSTALL_METHOD=remote
DIFY_PLUGIN_DAEMON_URL=http://localhost:5003
```

2. 确保 Dify 在本地运行（Docker Compose）

3. 启动插件：
```bash
python main.py
```

## 核心实现

### 已实现功能 ✅

**执行引擎** (`_execute_agent`):
- ✅ 动态系统提示生成（初始 vs 优化）
- ✅ 历史消息支持
- ✅ 流式和非流式 LLM 调用
- ✅ 工具调用处理
- ✅ 元数据收集（tokens、价格、延迟）

**评估系统** (`_evaluate_output`):
- ✅ LLM-as-judge 评估模式
- ✅ JSON 响应解析
- ✅ Fallback 机制
- ✅ 质量评分（0-100）

**优化循环** (`_invoke`):
- ✅ 迭代优化控制（max_refinements）
- ✅ 批判注入到下一轮执行
- ✅ 早停机制（质量达标时）
- ✅ 完整的日志和状态输出

**错误处理**:
- ✅ 参数验证（Pydantic）
- ✅ LLM 调用异常捕获
- ✅ 工具执行失败处理
- ✅ JSON 解析 fallback

### 待优化项
- [ ] 单元测试覆盖
- [ ] 性能基准测试
- [ ] 更多 prompt 模板变体
- [ ] 支持自定义评估标准

## 参考论文

Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., ... & Clark, P. (2023).
**Self-Refine: Iterative Refinement with Self-Feedback.**
NeurIPS 2023. [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)

## 许可证

MIT License

## 作者

KERVIN-FARMER
