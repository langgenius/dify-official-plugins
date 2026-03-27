### OpenAI Compatible

This extension converts your Dify app's API to OpenAI compatible API.

- **History**: You can set a `messages` parameter to your app to get the complete history of a OpenAI compatible API.

#### Steps to Create OpenAI Compatible API Endpoints

**Press the Add Endpoint Button**

Endpoint creation is done by clicking the "+" mark next to the endpoint of [Dify] ⇒ [Plugins] ⇒ [OpenAI Compatible Dify App].

**Configure the Endpoint**

Set the "Endpoint Name", "API Key", "App (Dify App)", and "Memory Mode".

| Item             | Description                                             | Notes                                                                                                                                       |
|-------------------|---------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| Endpoint Name     | Set a unique name for the endpoint to be registered.   | The endpoint name is not used elsewhere in this settings screen, so as long as it is unique, it is fine.                                    |
| API Key           | Enter the API key manually. It is recommended to generate a GUID or hash code for input. |                                                                                                                                             |
| App               | Specify the Dify app that has been created & published in the Dify studio. | Set apps compatible with Chat Completion such as chat flows, chatbots, agents, and text generators. Chat flows are fully supported.              |
| Memory Mode       | Choose between "Last User Message" or "All Messages".  | If you choose "All Messages", past messages in the thread will be sent to the large language model each time.                               |

#### Supported Endpoints

The only supported endpoint is Chat Completions. Endpoints like /models and /embeddings are not supported.

##### Endpoints

- /chat/completions  
  This is a Completions endpoint compliant with the OpenAI API standard. It supports both memory mode and both streaming and non-streaming, and supports Bearer API key authentication.

##### API Key

The API key set in [Dify] ⇒ [Plugins] ⇒ [OpenAI Compatible Dify App].

##### Model

In the OpenAI Compatible Dify App, specifying the model is not required; it will be ignored even if specified. Additionally, the model in the response when calling the Dify app through the OpenAI Compatible Dify App will always respond with gpt-3.5-turbo.

#### Actual Endpoints Provided

In the OpenAI Compatible Dify App, the actual endpoints provided per application are the endpoints created in the plugin settings. Individual Chat Completions endpoints will be created for each Dify app. The settings can be done from [Dify] ⇒ [Plugins] ⇒ [OpenAI Compatible Dify App]. To ensure the endpoints for each app are unique, the URLs will include a hash.

App 1: http://<your-dify-host>/e/c0odrljwgijfqlgl/chat/completions
App 2: http://<your-dify-host>/e/a7tags9tjz4d4e4o/chat/completions
