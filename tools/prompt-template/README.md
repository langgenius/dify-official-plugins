# Prompt Template — Dify Plugin

最简单的那种。就是一个 **变量替换器**。

就像大模型节点的 prompt 编辑框一样，2 个输入框（系统提示词模板 + 用户提示词模板），里面写 `{{变量名}}`，插件把它们替换成真实值输出。

## 和 PrePrompt Bridge 的区别

| | PrePrompt Bridge | Prompt Template |
|---|---|---|
| 定位 | 智能预处理：角色、模式、规则、上下文 | 纯模板渲染：变量替换 |
| 输入 | 十几个结构化参数 | 2 个文本框 + 额外变量 |
| 复杂度 | 高 | 极低 |
| 维护 | 有 | 无 |

## 安装

```bash
# 在 Dify 插件目录下
dify plugin install prompt-template/
```

## 使用

### 简易用法：替换 LLM 节点系统提示词

1. 在工作流中加入 **Prompt Template** 节点
2. 在 **系统提示词模板** 里写：

```
你是一个翻译助手。
今天的日期是 {{nodes.date.current}}。
目标语言：{{nodes.input.lang}}
```

3. 把输出的 `prompt` 传给 LLM 节点的系统提示词

### 完整用法：系统 + 用户提示词

1. **系统提示词模板**：写系统级提示词
2. **用户提示词模板**：写用户级提示词，例如：

```
根据以下信息回答问题。

背景信息：{{nodes.search.output}}

用户问题：{{nodes.input.text}}
```

3. 分别使用输出的 `system_prompt` 和 `user_prompt`

### 额外变量

如果有些变量在 Dify 的变量面板里选不到（比如某个节点的嵌套属性），用 **额外变量** 传入键值对。

## 输出

### 双输出模式（默认）

| 输出 | 含义 |
|------|------|
| `system_prompt` | 系统提示词模板渲染结果 |
| `user_prompt` | 用户提示词模板渲染结果 |

### 单输出模式（`system_only=true`）

| 输出 | 含义 |
|------|------|
| `prompt` | 仅 system_template 的渲染结果 |

## 就是这么简单

没有角色系统。没有模式系统。没有规则引擎。没有模板钩子。

就一个正则替换。
