## llamacloud

**Author:** langgenius
**Version:** 0.0.1
**Type:** extension

### Description

LlamaCloud is an online version of LlamaIndex with UI. 

If you are trying to build AI Agent with context retrieving capability and you are not primarily using Dify's Knowledge Base, you can use Dify's External Knowledge Base to connect with the RAG solution you prefer. This plugin will help you deploy your LlamaCloud Index as an endpoint so Dify External Knowledge Base can seamlessly connect with it.

To set up an Index in LlamaCloud, in the **Tools: Index** section, click on Create Index. 

<img src="./_assets/llamacloud_index_create.png" width="600" />

In the Index panel, you can upload your data, connect vector storage and embedding model, configure parse settings.
<img src="./_assets/llamacloud_index_panel.png" width="600" />

Once you set up your Index, you will get a Pipeline ID. 
<img src="./_assets/llama_cloud_pipeline_id.png" width="600" />

Generate an API Key here:
<img src="./_assets/llama_cloud_api_key.png" width="600" />

Now in Dify's marketplace, find LlamaCloud and install it.
Create a new endpoint by clicking here:
<img src="./_assets/llamacloud_add_endpoint.png" width="600" />

Give your endpoint a name, and paste the API Key we just created.
<img src="./_assets/name_endpoint.png" width="600" />

Copy the newly created Endpoint URL, go to Knowledge Base, "External Knowledge API", "Add an External Knowledge API", and paste the URL in "API Endpoint". 

**NOTICE: You must REMOVE the "/retrieval" in your URL!!!!!** For API Key, as we didn't configure any authorization, you can type in anything you want. So **PLEASE MAKE SURE NO ONE KNOWS THE ENDPOINT URL!!!**
<img src="./_assets/paste_url.png" width="600" />

Once your external knowledge base is connected, go to "connect to an external knowledge base", type in the Pipeline ID in "Knowledge ID", give it a name, and we are good to go.
<img src="./_assets/type_pipeline_id.png" width="600" />

Now you can do a retrieval test of your External Knowledge Base.
<img src="./_assets/retrieval_testing.png" width="600" />
