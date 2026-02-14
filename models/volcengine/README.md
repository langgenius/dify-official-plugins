# Volcengine Ark (Base Model)

This plugin calls **Volcengine Ark base models directly** (no custom inference endpoint required).

## Credentials

- `ark_api_key`: Ark API Key
- `api_endpoint_host`: default `https://ark.cn-beijing.volces.com/api/v3`

## Notes

- Models are listed as Ark **model ids** (e.g. `doubao-seed-1-6-251015`).
- E2E tests run against the predefined model list in `models/llm/_position.yaml`.
