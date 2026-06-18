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

**Phase 2: 文件骨架**
- ✅ 完整的目录结构
- ✅ manifest.yaml 配置
- ✅ provider 和 strategy 框架
- ✅ 基础测试消息
- ⏳ Phase 3: 完整实现（待开发）

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

## 开发计划

### Phase 3: 完整实现
- [ ] 实现 `_execute_agent_loop()` 方法
- [ ] 实现 `_evaluate_and_critique()` 评估器
- [ ] 添加 Prompt 模板（system/evaluation/refinement）
- [ ] 工具调用和错误处理
- [ ] 流式输出和日志消息
- [ ] 支持历史消息上下文

### Phase 4: 优化和测试
- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能优化
- [ ] 文档完善

## 参考论文

Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., ... & Clark, P. (2023).
**Self-Refine: Iterative Refinement with Self-Feedback.**
NeurIPS 2023. [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)

## 许可证

MIT License

## 作者

your-github-username

---

**注意**：当前为 Phase 2 骨架版本，仅用于结构验证。完整功能将在 Phase 3 中实现。
