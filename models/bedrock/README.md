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

## CloudWatch Request Metadata (Optional)
When enabled, attaches `dify_app_id` and `dify_source` as `requestMetadata` on Bedrock Converse API calls. This allows attributing individual invocations to a Dify app when querying CloudWatch model invocation logs.

- **Purpose**: Log attribution for per-request analysis. `requestMetadata` does not appear in Cost Explorer or on the bill.
- **Requirements**: Model invocation logging must be enabled on the AWS account.
- **Scope**: Only applies to Converse API calls (not other API types).
- **Default**: Disabled by default, opt-in via the credential setting.
- **How to enable**: Set the "Enable CloudWatch request metadata" option to "Enabled" in the provider or model credentials.

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

## Claude 4.5-Generation Models

The 4.5-generation Claude models — Sonnet 4.5 (`anthropic.claude-sonnet-4-5-20250929-v1:0`), Haiku 4.5 (`anthropic.claude-haiku-4-5-20251001-v1:0`), Opus 4.5 (`anthropic.claude-opus-4-5-20251101-v1:0`), Sonnet 4.6 (`anthropic.claude-sonnet-4-6`), Opus 4.6 (`anthropic.claude-opus-4-6-v1`), Opus 4.7 (`anthropic.claude-opus-4-7`), and Opus 4.8 (`anthropic.claude-opus-4-8`) — are inference-profile-only on Bedrock, like Claude 5. Key behaviors:

- **Invocable via `us.`, `eu.`, or `global.` cross-region inference profiles only.** No on-demand bare-ID invocation, and no `apac.` geo profile (unlike earlier Claude generations).
- **Plugin resolves the correct profile from your *Cross-Region Inference* selection:**
  - From US/Canada regions: `global` or `geographic` both work (the latter resolves to `us.`).
  - From EU regions: `global` or `geographic` both work (the latter resolves to `eu.`).
  - From APAC regions (e.g., `ap-northeast-1`): use `global`; `geographic` fails because no `apac.` profile exists for these models.
  - `disabled` always fails (ValidationException) for these models — they have no on-demand invocation.
- **Japan cross-region option:** Sonnet 4.6 and Opus 4.7 / 4.8 also support `japan`, which resolves to the `jp.` profile for data residency in Japan (requires region `ap-northeast-1` or `ap-northeast-3`). Sonnet 4.5, Haiku 4.5, and Opus 4.5 / 4.6 do not have a `jp.` profile.

## Japan data residency (`japan` cross-region inference)

Selecting `japan` for *Cross-Region Inference* uses the `jp.` geographic profile, which routes only to `ap-northeast-3` and `ap-northeast-1` — inference never leaves Japan. It requires the configured region to be one of those two, and the model to have a `jp.` profile (Sonnet 4.5 / 4.6, Haiku 4.5, Opus 4.7 / 4.8 and Nova Lite V2 at the time of writing). Otherwise the call fails with an explanatory error instead of silently routing elsewhere.

`geographic` is **not** equivalent: from Tokyo it resolves to `apac.`, which also routes to Korea, India, Singapore and Australia — and no `apac.` profile exists for 4.5-generation models or later. The pricing note above applies here too: displayed prices are the Global cross-region rates, and geo/in-region invocation is ~10% higher.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. See [PRIVACY.md](PRIVACY.md) for details.
