# Privacy

The TempGuru Dify plugin is designed for the strongest trust profile possible: nothing requested, nothing collected, nothing transmitted on the user's behalf beyond the public REST calls each tool makes.

## What this plugin does NOT do

- Does not collect personal data. No names, emails, phone numbers, addresses, or any other personal information.
- Does not require credentials. No API keys, OAuth tokens, passwords, or session cookies.
- Does not write data. Every tool wraps a `GET` request. No `POST`, `PUT`, `DELETE` operations.
- Does not execute scripts on the user's machine beyond the standard Dify plugin entrypoint.

## What the tools transmit

When invoked, each tool sends an HTTPS `GET` request to `https://mcp.tempguru.co/api/v1/<endpoint>` with the tool's parameters as URL query strings (e.g., `?city=Boston&date=2026-10-15`). No request body. The User-Agent header identifies the plugin as `tempguru-dify-plugin/0.0.1`.

The TempGuru backend logs standard HTTP request metadata (timestamp, IP, user-agent, request path) for security and uptime monitoring. No request body or response content is retained beyond standard ephemeral log retention. No tracking cookies, analytics pixels, or cross-site identifiers are used.

## What the tools return

The backend returns publicly published data:
- City coverage maps
- Role catalogs
- All-inclusive hourly rate ranges (W-2 wage + payroll taxes + workers comp + general liability)
- Lead-time guidance
- State-by-state compliance summaries

All of this data is also published at https://tempguru.co and can be inspected directly.

## Data residency

The TempGuru MCP REST API runs on Vercel's global edge network. Logs are stored in Vercel's US regions.

## Contact

Privacy questions: megan@tempguru.co
Full privacy policy: https://tempguru.co/privacy-policy
Terms of service: https://tempguru.co/terms-of-service
