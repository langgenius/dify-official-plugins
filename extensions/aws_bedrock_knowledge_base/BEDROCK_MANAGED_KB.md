# Bedrock Managed Knowledge Base Support

## Overview
Adds a Dify plugin extension that queries Amazon Bedrock Knowledge Bases for managed retrieval in Dify applications.

## Usage
In Dify application editor:
1. Install the **AWS Bedrock Knowledge Base** plugin
2. Configure AWS credentials and Knowledge Base ID in plugin settings
3. Use as a knowledge retrieval tool in Agent or Workflow apps

```yaml
plugin: aws_bedrock_knowledge_base
config:
  knowledge_base_id: "YOUR_KB_ID"
  region: "us-east-1"
  use_agentic_retrieval: true
  max_results: 5
```

## Configuration
| Variable | Description | Default |
|---|---|---|
| KNOWLEDGE_BASE_ID | Bedrock Knowledge Base ID | None |
| AWS_REGION | AWS region for the KB | us-east-1 |
| AWS_ACCESS_KEY_ID | AWS access key | None |
| AWS_SECRET_ACCESS_KEY | AWS secret key | None |
| USE_AGENTIC_RETRIEVAL | Enable agentic retrieval | true |
| MAX_RESULTS | Maximum retrieval results | 5 |

## Features
- Managed search (no vector store needed)
- Agentic retrieval with query decomposition + reranking
- Automatic fallback to plain Retrieve if agentic fails
- Multi-source support (S3, Web, Confluence, SharePoint)
- Configurable via Dify plugin settings UI

## SDK Requirements
- boto3 >= 1.43
- dify-plugin-sdk >= 0.1

## Required IAM Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:Retrieve",
    "bedrock:AgenticRetrieveStream"
  ],
  "Resource": "arn:aws:bedrock:<region>:<account-id>:knowledge-base/<kb-id>"
}
```

## References
- [Build a Managed Knowledge Base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- [Retrieve API](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve.html)
- [Agentic Retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic.html)
