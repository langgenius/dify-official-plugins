# Introduction

A Dify plugin that integrates the [Dingo](https://github.com/MigoXLab/dingo/) data quality evaluation library to help automatically detect data quality issues in datasets and text content.

## Features

- **Text Quality Evaluation**: Assess the quality of text content using built-in rules from the Dingo library
- **Multiple Rule Groups**: Support for different evaluation rule sets (default, sft, rag, hallucination, pretrain)
- **Quality Scoring**: Get numerical quality scores (0-100%) with detailed issue reports
- **Simple Integration**: Easy to use within Dify workflows, chatflows, and agent applications
- **Local Processing**: All evaluation happens locally, no external API calls required

## Usage

1. Install the plugin in your Dify workspace
2. Add the "Text Quality Evaluator" tool to your workflow
3. Configure the tool parameters:
   - **Text Content**: The text you want to evaluate
   - **Rule Group**: Choose between "default", "sft", "rag", "hallucination", or "pretrain" rule sets
4. Get comprehensive quality assessment results including:
   - Overall quality score percentage
   - Number of issues detected
   - Detailed list of specific problems found

## Example Use Cases

- **Content Moderation**: Evaluate user-generated content for quality issues
- **Data Preprocessing**: Clean datasets before training or analysis
- **RAG System Enhancement**: Improve retrieval quality by filtering low-quality documents
- **Content Creation**: Validate generated text meets quality standards

## Rule Groups

The plugin supports different rule groups optimized for specific use cases:

| Group | Use Case | Description |
|-------|----------|-------------|
| `default` | General text quality | Basic quality checks including content completeness, formatting issues |
| `sft` | Fine-tuning datasets | Rules from default plus hallucination detection for supervised fine-tuning |
| `rag` | RAG system evaluation | Response consistency and context alignment assessment |
| `hallucination` | Hallucination detection | Specialized rules for detecting AI-generated content issues |
| `pretrain` | Pre-training datasets | Comprehensive set of 20+ rules for large-scale dataset evaluation |

## About Dingo

[Dingo](https://github.com/MigoXLab/dingo/) is a comprehensive data quality evaluation tool that helps you automatically detect data quality issues in your datasets. Dingo provides a variety of built-in rules and model evaluation methods, and also supports custom evaluation methods. It supports commonly used text datasets and multimodal datasets, including pre-training datasets, fine-tuning datasets, and evaluation datasets.

### Key Features of Dingo:
- **Multi-source & Multi-modal Support**: Local files, Hugging Face datasets, S3 storage
- **Rule-based & Model-based Evaluation**: 20+ built-in rules, LLM integration, hallucination detection
- **Comprehensive Reporting**: 7-dimensional quality assessment with detailed traceability

## Contact & Support

- **Plugin Repository**: [dingo-plugin](https://github.com/dingo/dingo-plugin)
- **Original Dingo Project**: [DataEval/dingo](https://github.com/DataEval/dingo)
- **Issues & Feedback**: Please report issues on the plugin repository
- **Discord**: [Join Dingo Community](https://discord.gg/Jhgb2eKWh8)
- **Online Demo**: [Try Dingo on Hugging Face](https://huggingface.co/spaces/DataEval/dingo)

## License

This project uses the [Apache 2.0 Open Source License](LICENSE).

## Privacy Policy

This plugin processes text data locally within your Dify environment. No data is transmitted to external servers. See [privacy-policy.md](privacy-policy.md) for full details.
