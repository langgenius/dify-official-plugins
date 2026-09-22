# Amazon SageMaker

Self deployed model provider - Amazon SageMaker.

## Features
- Provides llm, text-embedding, rerank, speech2text, tts models in Dify.
- Supports customizable model configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get the required credentials from [Amazon SageMaker](https://github.com/aws-samples/dify-aws-tool/blob/main/README.md#how-to-deploy-sagemaker-endpoint).
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Usage
Select **Amazon SageMaker** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Cross-account access (AssumeRole)
Set the optional **Assume Role ARN** field (for example `arn:aws:iam::TARGET-ACCOUNT-ID:role/SageMakerCrossAccountRole`) when the SageMaker endpoint lives in a different AWS account.
- The plugin builds a session from the source-account credentials (the explicit Access Key / Secret Access Key when both are set, otherwise the runtime environment's default credential chain), calls `sts:AssumeRole` on that ARN, and invokes the endpoint with the temporary credentials. The credentials are refreshed automatically before they expire, and every refresh re-assumes the role with the same source identity.
- The target role must trust the source identity and allow `sagemaker:InvokeEndpoint` (plus `s3`/`comprehend` access for speech2text and tts). STS sessions are named `dify-sagemaker-embedding-<ts>`, `dify-sagemaker-rerank-<ts>` or `dify-sagemaker-<ts>` for CloudTrail auditing.
- Leave the field empty to keep the previous behaviour: the endpoint is invoked directly with the source-account credentials and no STS call is made.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. See [PRIVACY.md](PRIVACY.md) for details.
