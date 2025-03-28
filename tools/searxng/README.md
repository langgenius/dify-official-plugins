# Overview
**SearXNG** is a free and open-source metasearch engine that aggregates results from multiple search services and databases. It prioritizes user privacy by ensuring that no tracking or profiling occurs. SearXNG allows users to perform searches anonymously while retrieving comprehensive results from various sources.

When integrated with Dify, SearXNG can be used as a tool to enhance search capabilities within your workflows. This integration enables you to query multiple search engines simultaneously and retrieve aggregated results directly in Dify.

# Configure
## 1. Prerequisites
Before starting, ensure the following:
- Access to the Dify Community Edition or the ability to configure tools in Dify Cloud.
- Docker installed on your system for local deployment.
- The SearXNG service is either self-hosted or accessible via a public instance.
- Install SearXNG from Dify Marketplace.

## 2. Local Deployment Using Docker

### Step 1: Start the SearXNG Docker Service
```shell
$ mkdir my-instance
$ cd my-instance
$ export PORT=8081
$ docker pull searxng/searxng
$ docker run --rm \
             -d -p ${PORT}:8080 \
             -v "${PWD}/searxng:/etc/searxng" \
             -e "BASE_URL=http://localhost:$PORT/" \
             -e "INSTANCE_NAME=my-instance" \
             searxng/searxng
2f998.... # container's ID
```
> Note: Use port `8081` instead of `8080` to avoid conflicts with other Docker services.

### Step 2: Modify the SearXNG Configuration

Edit the `my-instance/searxng/settings.yml` file,  make sure the `formats` has `json` format(default is only `html`) and the `limiter` is `false`.

Then restart the SearXNG Docker service.
```shell
$ docker restart 2f998
```

### Step 3: Authenticate in Dify
1. Go to **Tools > SearXNG > To authorize** in your Dify dashboard.
2. Enter the base URL for your SearXNG instance, typically:
`http://host.docker.internal:8081`
3. Save the configuration to establish a connection between Dify and SearXNG.


## 3. Using an Existing SearXNG Instance
If you are using an already deployed SearXNG service (e.g., on a public server), follow these steps:
1. Retrieve the base URL of your SearXNG instance.
2. Navigate to **Tools > SearXNG > To authorize** in Dify.
3. Input the base URL and save the configuration.
