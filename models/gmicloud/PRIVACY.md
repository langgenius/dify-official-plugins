# Privacy Policy

This Privacy Policy explains how we collect, use, and protect your information when you use the GMI Cloud Model Provider Plugin for Dify.

## Information Collection

We do not collect, store, or share any personal information from users. All data processed by the plugin is handled through secure connections to GMI Cloud's AI inference services, as required for functionality.

## Use of Information

The plugin accesses and transmits the following information to provide AI inference services:
- User prompts and chat messages sent to AI models
- Model configuration parameters (temperature, top_p, max_tokens, etc.)
- System prompts and conversation context
- Tool calling requests and function definitions (when applicable)
- Streaming preferences and response formatting options

No personal data is collected, stored, or transmitted to third parties by the plugin itself beyond what is necessary for AI inference.

## Data Processing

When using this plugin:
- **Prompt Transmission**: Your input prompts are sent to GMI Cloud's inference API for processing
- **Model Inference**: AI models hosted on GMI Cloud's GPU infrastructure generate responses
- **Response Delivery**: Generated responses are returned through the plugin to your Dify application
- **Temporary Processing**: Data is processed in real-time and not permanently stored by the plugin
- **Tool Calling**: When enabled, function calls and tool use requests are processed by GMI Cloud's models

## Third-Party Services

This plugin interacts with GMI Cloud's AI inference services:
- **Service Endpoint**: 
  - Default: `https://api.gmi-serving.com/v1`
  - Custom endpoints available for enterprise deployments
- **Service Provider**: GMI Cloud (https://gmicloud.ai)
- Please refer to [GMI Cloud's Privacy Policy](https://www.gmicloud.ai/privacy-policy) for details on how your data is handled by GMI Cloud services

**Important**: All prompts, responses, and usage data transmitted through this plugin are subject to GMI Cloud's own privacy policy, terms of service, and data processing practices.

## API Key Usage

- **Required Authentication**: API key is required to access GMI Cloud services
- **Secure Transmission**: API keys are transmitted securely via HTTPS headers
- **Dify Storage**: API keys are stored securely within your Dify instance according to Dify's security practices
- **No Key Logging**: The plugin does not log, cache, or permanently store your API key beyond Dify's configuration

## Data Security

We are committed to ensuring the security of your data:
- All communications with GMI Cloud services use secure HTTPS protocols
- Authentication tokens (when provided) are handled securely
- No crawled content is permanently stored by the plugin
- Data is transmitted directly between your system and GMI Cloud services

## Model Access Scope

The plugin provides access to:
- Multiple AI model families (DeepSeek, Llama, Qwen, Zhipu/GLM, OpenAI OSS)
- Chat completion endpoints with streaming support
- Tool calling and function execution capabilities
- Custom model configurations and parameters
- Organization-specific custom endpoints

The plugin does NOT:
- Access password-protected or private content
- Share your data with any third parties other than GMI Cloud
- Access content beyond the specified limits
- Access or modify data outside of the API request/response cycle

## User Rights

You have the right to:
- Choose which AI models to use from the available options
- Configure model parameters to control output behavior
- Use custom API endpoints for enterprise deployments
- Revoke API access by removing credentials from Dify
- Control what data is sent to the AI models through your application logic
- Switch to alternative model providers at any time

## Compliance

This plugin and GMI Cloud services should be evaluated for:
- Data protection regulations (GDPR, CCPA, etc.)
- Industry-specific compliance requirements
- Organizational data handling policies
- Cross-border data transfer regulations

Please consult GMI Cloud's documentation and your organization's compliance team for specific regulatory requirements.

## Data Retention

- **Temporary Logging (7 Days)**: For tracing and debugging purposes, request and response metadata may be securely logged and retained for up to 7 days before automatic deletion.
- **Session Data**: Request/response data exists only during active API calls
- **Configuration Only**: Only your API key and endpoint configuration are persistently stored (in Dify)
- **GMI Cloud Retention**: Please refer to GMI Cloud's privacy policy for their data retention practices

## Third-Party Data Processing

**Critical Notice**: When you use this plugin, your data is processed by GMI Cloud's infrastructure. You should:
- Review GMI Cloud's terms of service and privacy policy
- Understand how GMI Cloud handles, stores, and potentially uses your data
- Verify GMI Cloud's compliance certifications match your requirements
- Ensure your users are aware that their data is processed by a third-party AI service
- Consider data residency and sovereignty requirements for your use case

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer at [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

For questions about how GMI Cloud handles your data, please contact GMI Cloud directly through their support channels at https://gmicloud.ai.

Last updated: November 2025