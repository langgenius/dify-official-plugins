# Amazon Bedrock

The models of Amazon Bedrock.

## Features
- Provides llm, text-embedding, rerank models in Dify.
- Includes predefined llm models such as openai, mistral, ai21.
- Includes predefined rerank models such as amazon.rerank-v1, cohere.rerank-v3-5.
- Includes predefined text embedding models such as cohere.embed-multilingual-v3, cohere.embed-english-v3, amazon.titan-embed-text-v2.
- Supports predefined model and customizable model configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get the required credentials from [Amazon Bedrock](https://console.aws.amazon.com/).
3. Add the credentials in the plugin settings.
4. Save the configuration.

### Temporary Credentials
The plugin supports AWS temporary credentials from SSO/SAML authentication (e.g., `aws sso login` or `saml2aws login`):

- **Access Key authentication**: optionally provide an AWS Session Token for temporary credentials. The plugin will use the session token alongside your access key and secret key.
- **IAM Role authentication**: credentials are automatically refreshed on every invocation. The plugin creates a fresh boto3 session for each IAM Role authentication call, which picks up the latest credentials from disk (via `saml2aws login`, `aws sso login`, IMDS, etc.). This proactive approach eliminates `ExpiredTokenException` errors and makes credential rotation transparent without requiring plugin daemon restarts.

## Usage
Select **Amazon Bedrock** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Claude 5 Models (Opus 5 / Sonnet 5 / Fable 5)

The "Anthropic Claude 5" entry provides Claude Opus 5 (`anthropic.claude-opus-5`), Claude Sonnet 5 (`anthropic.claude-sonnet-5`), and Claude Fable 5 (`anthropic.claude-fable-5`). These models differ from earlier Claude generations:

- **Inference profiles only.** Invocable exclusively via cross-region inference profiles — there is no on-demand bare-ID invocation. Geographic profile coverage varies per model: Opus 5 and Sonnet 5 offer `us.` (also serves Canada regions), `eu.`, and `au.` profiles; Fable 5 offers `us.` only. `global.` works from virtually all commercial regions. The plugin resolves this from your *Cross-Region Inference* selection; when your region has no geo profile, choose `global`.
- **Adaptive thinking is on by default.** Thinking depth is controlled by the *Effort* parameter (`low`/`medium`/`high`/`xhigh`/`max`) instead of a thinking budget. Sampling parameters (temperature / top_p / top_k) are not configurable on these models and are not exposed.
- **Refusals & fallback.** Requests can be declined by safety classifiers (`stop_reason: refusal`; materially more frequent on Fable 5). With *Refusal Fallback* enabled (default), the plugin automatically retries the identical request with Claude 4.8 Opus. Mid-stream refusals that occur after output has been produced cannot fall back and raise an error instead.
- **Fable 5 prerequisite: data retention opt-in.** Your AWS account must set data retention mode to `provider_data_share` via the Bedrock Data Retention API before invoking Fable 5 (no console UI at launch). See the [Fable 5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5.html). The plugin never changes account settings.
- **Pricing note.** Displayed prices are the Global cross-region rates (Opus 5 $5/$25, Sonnet 5 $3/$15, Fable 5 $10/$50 per 1M tokens). Geo/in-region invocation is ~10% higher. Prompt-cache read/write rates are not representable in Dify's cost tracking — refer to your AWS bill.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. See [PRIVACY.md](PRIVACY.md) for details.
