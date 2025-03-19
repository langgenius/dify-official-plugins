This privacy policy explains how the AWS Bedrock Knowledge Base Endpoint plugin ("the plugin") handles data when connecting Dify with AWS Bedrock Knowledge Base.

### Data Collection and Transmission

The plugin acts as a connector between Dify and AWS Bedrock Knowledge Base and:

- Does not store any data locally or persistently within the plugin
- Transmits all data securely via HTTPS protocol
- Only processes data temporarily in memory during request handling

### Data Handled

The following types of data pass through the plugin:

1. AWS Credentials:
   - AWS Access Key ID
   - AWS Secret Access Key
   - Region Name
   These credentials are stored and managed by Dify's secure credential storage system.

2. Query Data:
   - Search queries and parameters sent from Dify to AWS Bedrock
   - Search results returned from AWS Bedrock to Dify
   This data is stored and managed by Dify and AWS according to their respective privacy policies.

### Data Storage

- The plugin itself maintains no data storage
- All persistent data storage is handled by either:
  - Dify (credentials, queries, results)
  - AWS Bedrock (knowledge base content, search indices)

### Third-Party Services

This plugin relies on:
- AWS Bedrock Knowledge Base service
- Dify

Users should refer to the privacy policies of these services for information about how they handle data:
- AWS Privacy Notice (https://aws.amazon.com/privacy/)
- Dify's privacy policy (https://dify.ai/privacy)
