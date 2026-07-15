# Privacy

This plugin sends the files, URLs, settings, and credentials needed to perform the selected action to the Unstructured endpoint configured by the user. The plugin does not add its own persistent data store.

When **Unstructured Transform** is selected, files and public URLs are processed by the hosted Unstructured Transform service. When a Partition API option is selected, data is sent to the configured Unstructured API or self-hosted endpoint. Processing and retention by hosted Unstructured services are governed by the [Unstructured Privacy Policy](https://unstructured.io/privacy-policy) and the customer's agreement with Unstructured.

API keys are used only to authenticate requests to the configured endpoint. Do not place API keys in workflow inputs or prompts; store them in the plugin credential fields.

Dify may retain workflow inputs and outputs according to the user's Dify deployment and policies. Review Dify's privacy and data-retention settings separately.
