# Dealport Plugin for Dify

Dealport is the SMB knowledge layer for agents and humans, indexing 28M+ US private companies, commercial and multifamily buildings, primary public-filing citations, living Projects, Playbooks, and verified human owner contacts.

## Setup

1. Sign in to [Dealport Connect](https://app.dealport.com/connect?tab=keys) and create a workspace API key (`dp_live_...`). New pay-as-you-go API accounts start with a `$5.00` free balance.
2. In Dify, install the **Dealport** tool plugin and paste your `dp_live_...` API key. Dify validates your key against `GET /api/v1/balance` (`$0.00`).

## Included Tools & Plain-USD Rates

| Tool | Endpoint | Plain-USD Rate |
| --- | --- | --- |
| `preview_companies` | `POST /api/v1/companies/preview` | `$0.00` free market sizing count and 5 sample companies |
| `search_companies` | `GET /api/v1/companies` | `$0.01` per new Record (`$0.00` repeat within 30 days) |
| `search_buildings` | `GET /api/v1/buildings` | `$0.01` per new Record |
| `get_record` | `GET /api/v1/records/{id}` | `$0.01` per new Record |
| `find_owner` | `POST /api/v1/owners` | `$0.09` per verified hit (`$0.00` miss) |
| `match_company_list` | `POST /api/v1/companies/match` | `$0.00` entity matching against 28M+ US companies |

## Links

- Website: https://dealport.com
- OpenAPI 3.1 Spec: https://app.dealport.com/openapi/v1.json
- LLM & Agent Reference: https://app.dealport.com/llms.txt
