# TempGuru Event Staffing — Dify Plugin

Read-only W-2 event staffing data for AI agents across 300+ US and Canadian markets. Brand ambassadors, registration, hospitality, setup/breakdown, ushers, and more. No authentication required — connect with no API key.

## What it does

Wraps the public TempGuru MCP REST API (`https://mcp.tempguru.co/api/v1/*`) as 5 read-only Dify tools, so an agent built on Dify can answer event-staffing questions without leaving the workflow.

## Tools

| Tool | Returns |
|---|---|
| `get_cities` | All cities TempGuru staffs, with tier classification (hub/mid/small). Filter by state or tier. |
| `get_roles` | Event staffing roles with descriptions and skill tiers. |
| `check_availability` | Lead-time guidance for a city + date. Not real-time inventory. |
| `get_role_pricing` | All-inclusive hourly rate range for a role in a city. Includes W-2 wages, workers comp, taxes. |
| `get_compliance_by_state` | US state-level minimum wage, overtime, compliance summary. Not legal advice. |

## Typical agent prompts this plugin answers

- "Hire 25 registration staff for a 3-day conference in Dallas — what does that cost and how far in advance do I need to book?"
- "What's the rate for brand ambassadors in San Francisco?"
- "What cities do you cover in the Northeast?"
- "What are the W-2 vs 1099 rules for event workers in California?"
- "Can you staff a corporate event in Boston on 2026-10-15?"

## Trust profile

- **Read-only** — every tool wraps a `GET` request; no `POST`, `PUT`, `DELETE`, or write operations exist
- **No authentication** — public data, no API key, no OAuth, no user credentials
- **No data collection** — the plugin does not persist user inputs, queries, or outputs
- **No executable scripts** — only the standard Dify plugin entrypoint
- **Same data as the public site** — every response comes from TempGuru's published rate cards, coverage maps, and compliance summaries at https://tempguru.co

## Important disclaimers

- **Rates are all-inclusive planning estimates**, not binding quotes. Binding quotes come from the contact form on tempguru.co — they include event-specific factors (location surcharges, weekend/holiday premiums, security, equipment) that the public rate range doesn't capture.
- **Compliance summaries are not legal advice.** For W-2 vs 1099 classification, joint-employer liability, or state-specific wage and hour questions, consult employment counsel.
- **Availability is lead-time math, not real-time inventory.** TempGuru staffs to demand from a 100,000+ W-2 worker network.
- **Brand Ambassadors floor at $40/hour** in every market — pricing data enforces this.

## Other distribution surfaces

- Direct MCP connection: `https://mcp.tempguru.co/mcp` (streamable HTTP, MCP spec rev 2025-03-26)
- Official MCP Registry: `co.tempguru/event-staffing` (DNS-verified)
- Smithery: [`tempguru/event-staffing`](https://smithery.ai/server/tempguru/event-staffing)
- ModelScope MCP Plaza: [`tempguru/TempGuru-Event-Staffing`](https://modelscope.cn/mcp/servers/tempguru/TempGuru-Event-Staffing/)
- Documentation: https://tempguru.co/ai (English) · https://tempguru.co/zh-cn/ai (Chinese)
- Source repository: https://github.com/kissmyabs32/tempguru-mcp

## License

MIT
