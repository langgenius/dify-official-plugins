## Overview

[LocalAI](https://github.com/go-skynet/LocalAI) is a drop-in replacement REST API that's compatible with OpenAI API specifications for local inferencing. It allows you to run LLMs (and not only) locally or on-prem with consumer grade hardware, supporting multiple model families that are compatible with the ggml format. Does not require GPU.

Dify allows integration with LocalAI for local deployment of large language model inference and embedding capabilities.

## Configure

1. First, clone the LocalAI code repository and navigate to the specified directory.
```
$ git clone https://github.com/go-skynet/LocalAI$ cd LocalAI/examples/langchain-chroma
```

2. Download example LLM and Embedding models.
```
$ wget https://huggingface.co/skeskinen/ggml/resolve/main/all-MiniLM-L6-v2/ggml-model-q4_0.bin -O models/bert$ wget https://gpt4all.io/models/ggml-gpt4all-j.bin -O models/ggml-gpt4all-j
```
Here, we choose two smaller models that are compatible across all platforms. `ggml-gpt4all-j` serves as the default LLM model, and `all-MiniLM-L6-v2` serves as the default Embedding model, for quick local deployment.

3. Configure the .env file.
```
$ mv .env.example .env
```
NOTE: Ensure that the THREADS variable value in `.env` doesn't exceed the number of CPU cores on your machine.

4. Start LocalAI.
```
# start with docker-compose$ docker-compose up -d --build
# tail the logs & wait until the build completes$ docker logs -f langchain-chroma-api-17:16AM INF Starting LocalAI using 4 threads, with models path: /models7:16AM INF LocalAI version: v1.24.1 (9cc8d9086580bd2a96f5c96a6b873242879c70bc)
```

The LocalAI request API endpoint will be available at [http://127.0.0.1:8080](http://127.0.0.1:8080).

And it provides two models, namely:
  - LLM Model: `ggml-gpt4all-j`
  - External access name: `gpt-3.5-turbo` (This name is customizable and can be configured in `models/gpt-3.5-turbo.yaml`).
  - Embedding Model: `all-MiniLM-L6-v2`
  - External access name: `text-embedding-ada-002` (This name is customizable and can be configured in `models/embeddings.yaml`).

> If you use the Dify Docker deployment method, you need to pay attention to the network configuration to ensure that the Dify container can access the endpoint of LocalAI. The Dify container cannot access localhost inside, and you need to use the host IP address.

5. Integrate the models into Dify.
Go to `Settings > Model Providers > LocalAI` and fill in:
Model 1: `ggml-gpt4all-j`
- Model Type: Text Generation
- Model Name: `gpt-3.5-turbo`
- Server URL: [http://127.0.0.1:8080](http://127.0.0.1:8080)
- If Dify is deployed via docker, fill in the host domain: `http://<your-LocalAI-endpoint-domain>:8080`, which can be a LAN IP address, like: [http://192.168.1.100:8080](http://192.168.1.100:8080)
Click "Save" to use the model in the application.
Model 2: `all-MiniLM-L6-v2`
  - Model Type: Embeddings
  - Model Name: `text-embedding-ada-002`
  - Server URL: [http://127.0.0.1:8080](http://127.0.0.1:8080)
    - If Dify is deployed via docker, fill in the host domain: `http://<your-LocalAI-endpoint-domain>:8080`, which can be a LAN IP address, like: [http://192.168.1.100:8080](http://192.168.1.100:8080)

Click "Save" to use the model in the application.

For more information about LocalAI, please refer to: [https://github.com/go-skynet/LocalAI](https://github.com/go-skynet/LocalAI)