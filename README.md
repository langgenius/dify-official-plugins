test

### Introduction

[Dify](https://dify.ai/) is an open-source platform for developing LLM-powered AI applications, designed to help developers and businesses efficiently build, deploy, and manage AI-driven solutions. With Dify, users can easily create and test complex AI workflows, integrate a wide range of advanced models and tools, and optimize their performance in real-world applications. The platform offers an intuitive interface, supporting RAG (Retrieval-Augmented Generation) pipelines, intelligent agent capabilities, and robust model management, enabling developers to seamlessly transition from prototype to production. 

Dify's models and tools were originally stored in the [main Dify repository](https://github.com/langgenius/dify). However, starting from Dify v1.0.0 (February 2025), all models and tools have been migrated into plugins and are now stored in this repository. All plugins in this repository will be uploaded to the [Dify Marketplace](https://marketplace.dify.ai/), where they will be maintained and updated by the official Dify team. The plugins in the Marketplace are available for all Dify users to explore and use.

### Plugin Types

#### Models

Models transform AI model management in Dify. Now you can configure, update and use models as plugins across chatbots, agents, chatflows and workflows.

#### Tools

Tools add specialized capabilities to Dify apps. Enhance your agents and workflows with domain-specific features for data analysis, content translation, custom integrations and more.

#### Agent Strategies

Agent Strategies provide reasoning strategies for the new [**Agent Nodes**](https://docs.dify.ai/guides/workflow/node/agent) in Dify chatflows / workflows, supporting autonomous tool selection and execution for multi-step reasoning. Create custom reasoning strategies like Chain-of-Thoughts, Tree-of-Thoughts, Function call and ReAct to enhance the problem-solving abilities of your chatflows / workflows.

#### Extensions

Extensions facilitate external integrations through HTTP webhooks. Build custom APIs to handle complex workflows, process data, or connect with external services, making your applications more versatile and powerful.

### Update

In the future, all new official plugins developed by Dify will be updated and maintained in this repository.

### Dependency Management

Python plugins should declare dependencies in `pyproject.toml` and commit the generated `uv.lock`. After changing dependencies, run `uv lock` and commit both files. Use `uv sync --frozen` from the plugin directory to reproduce the locked environment.

During the migration from `requirements.txt`, legacy plugins without `uv.lock` may keep using `requirements.txt`. CI/CD uses `uv.lock` first and falls back to `requirements.txt` only when no lock file is present.

### Security disclosure

To protect your privacy, please avoid posting security issues on GitHub. Instead, send your questions to [security@dify.ai](mailto:security@dify.ai) and we will provide you with a more detailed answer.
