from openai import AzureOpenAI, Omit, OpenAI


def create_image_client(credentials: dict) -> tuple[OpenAI, dict]:
    endpoint = credentials["azure_openai_base_url"].strip().rstrip("/")
    api_key = credentials["azure_openai_api_key"]
    version = (credentials.get("azure_openai_api_version") or "").strip()
    if version and version != "v1":
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=version,
            azure_deployment=credentials["azure_openai_api_model_name"],
        )
        return client, {}

    client = OpenAI(
        api_key=api_key,
        base_url=f"{endpoint.removesuffix('/openai/v1')}/openai/v1/",
        default_query={"api-version": "preview"},
    )
    return client, {"extra_headers": {"api-key": api_key, "Authorization": Omit()}}
