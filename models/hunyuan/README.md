# Hunyuan

Tencent Hunyuan models for chat, image generation, and text embeddings.

## Credentials

- For Hy4, Hy4 Flash, Hy3, and Hy-Image 3.5 Preview, enter a Guangzhou TokenHub API key and enable the models you want to use in the [TokenHub console](https://console.cloud.tencent.com/tokenhub/apikey).
- For the earlier Hunyuan chat models and text embeddings, enter your Tencent Cloud [Secret ID and Secret Key](https://console.cloud.tencent.com/cam/capi).
- Enter both sets of credentials in the Hunyuan model provider settings if you use both APIs.

For new chat workflows, select a TokenHub model. Tencent Cloud has retired several older model IDs and lists December 21, 2026 as the planned shutdown date for the legacy chat API. [Legacy chat API status](https://cloud.tencent.com/document/product/1729/105701).

## Usage

Select **Hunyuan** as the model provider in Dify. To generate an image, select **Hy-Image 3.5 Preview** in an LLM node and enter a prompt. Enable vision to supply a reference image. For a follow-up edit, provide the previous image as a new reference. Download or store the result before Tencent Cloud's signed URL expires.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.
