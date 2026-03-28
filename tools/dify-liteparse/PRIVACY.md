## Privacy Policy

**LiteParse Document Parser for Dify**

### 1. Data Processing
This plugin acts as a bridge between your Dify workflow and the **LlamaCloud (LlamaIndex)** API. When you use this tool:
* **Document Data:** The document files you upload are sent to LlamaCloud's servers for parsing and processing.
* **Processing:** The extraction and conversion to Markdown occur on LlamaCloud's infrastructure.
* **API Keys:** Your LlamaCloud API Key is handled securely as a `secret-input` within Dify and is only used to authenticate requests to the LlamaCloud API.

### 2. Data Storage
* **No Local Storage:** This plugin does not store your documents, API keys, or parsed text on its own servers. 
* **Dify Environment:** Data persistence is managed entirely by your Dify instance and LlamaCloud's specific retention policies.

### 3. Third-Party Terms
By using this plugin, you agree to the data handling practices of **LlamaIndex (LlamaCloud)**. We recommend reviewing their official privacy documentation regarding how they handle uploaded files:
* [LlamaIndex Privacy & Terms](https://www.llamaindex.ai/privacy)

### 4. Security
We recommend using environment variables or Dify's built-in secret management to handle your API keys. Never share your LlamaCloud API key in public logs or shared workflow configurations.