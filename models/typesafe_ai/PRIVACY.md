# Privacy

This plugin sends the classifier query, rendered conversation history, classification instructions and category IDs/descriptions to the TypeSafe AI API (`https://api.typesafe.ai`) using the API key configured in Dify. Credential validation calls the same service's model-list endpoint. Single-category classifications do not send data upstream.

The plugin does not persist requests or API keys and does not log prompt contents or upstream error bodies. Dify manages configured credentials and workflow records; TypeSafe AI's service policies govern data sent to its API. This plugin does not add a retention policy on behalf of either service.
