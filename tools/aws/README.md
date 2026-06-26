# AWS Tools

The tools based on the AWS Services.

## Features
- Bedrock Retrieve: A tool for retrieving relevant information from Amazon Bedrock Knowledge Base. You can find deploy instructions on Github Repo - https://github.com/aws-samples/dify-aws-tool.
- Bedrock Retrieve and Generate: This is an advanced usage of Bedrock Retrieve. Please refer to the API documentation for detailed parameters and paste them into the corresponding Knowledge Base Configuration or External Sources Configuration.
- OpenSearch Retrieve: A tool for retrieving relevant information from Amazon OpenSearch.
- AWS S3 Operator: AWS S3 Writer and Reader.
- AWS S3 File Uploader: Upload a workflow file (file variable) to S3 and optionally return a presigned URL.
- AWS S3 File Download: Download an S3 object as a Dify file variable for downstream nodes.
- AWS S3 Batch File Uploader: Upload multiple workflow files (`input_files: files`) to S3 in a single invocation, with per-file presigned URLs and per-file failure isolation.
- AWS S3 Batch File Download: Download multiple S3 objects (`s3_uris: array` of `s3://...` URIs) as Dify file variables in a single invocation, with per-URI failure isolation.
- Content Moderation Guardrails: Content Moderation Guardrails utilizes the ApplyGuardrail API, a feature of Guardrails for Amazon Bedrock. This API is capable of evaluating input prompts and model responses for all Foundation Models (FMs), including those on Amazon Bedrock, custom FMs, and third-party FMs. By implementing this functionality, organizations can achieve centralized governance across all their generative AI applications, thereby enhancing control and consistency in content moderation.
- AWS Bedrock Nova Canvas: A tool for generating and modifying images using AWS Bedrock's Nova Canvas model. Supports text-to-image, color-guided generation, image variation, inpainting, outpainting, and background removal. Input parameters reference https://docs.aws.amazon.com/nova/latest/userguide/image-gen-req-resp-structure.html.
- TranscribeASR: A tool for ASR (Automatic Speech Recognition) - https://github.com/aws-samples/dify-aws-tool.
- TranslateTool: A util tools for LLM translation, extra deployment is needed on AWS. Please refer Github Repo - https://github.com/aws-samples/rag-based-translation-with-dynamodb-and-bedrock.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Open the plugin settings in Dify.
3. Save the configuration.

## Usage
Add the AWS Tools tools to an agent or workflow, fill in the required inputs, and run the node to call the upstream service.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. See [PRIVACY.md](PRIVACY.md) for details.
