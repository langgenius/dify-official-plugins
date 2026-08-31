<!-- DO NOT EDIT — generated from truth/ by scripts/gen.mjs -->
<!-- truth-sha: 540d5ca39fd40903 -->
<!-- Edit truth/service.json or truth/tools.json instead, then run: node scripts/gen.mjs -->

# Truth Bear for Dify

Truth Bear returns official-source records for AI agents: every record carries the official source URL, a record_hash you can recompute offline, a freshness stamp, and a did:key signature.

## Tools

- **verify_citation** — FREE. Given a record_hash from any Truth Bear record, look it up and recompute the canonical hash server-side, returning whether it is a genuine Truth Bear offi
- **find_signal** — FREE coverage + freshness manifest: which signal_id lines exist, how many entities each covers, and fresh/recent/stale counts - so you can check "is my entity c
- **get_official_record** — Returns the REAL x402 payment challenge (accepts[]: network / asset / payTo / amount) for the paid endpoint that serves a given signal_id+entity, or any listed 
- **purchase_options** — FREE. Ask how to pay for a listed endpoint and get every channel with its REAL status - including the ones that are wired but not open yet. Three channels exist

## Setup

1. In Dify, go to **Plugins → Explore Marketplace**, search for **Truth Bear**, and install it.
   (Or install the `.difypkg` directly via **Plugins → Install plugin → Local Package File**.)
2. No credential setup is required. There is no API key, no account, and no wallet to connect —
   see **Credentials** below.
3. Add the plugin's tools to an Agent or a Workflow node and call them.

## Usage

- **Check coverage first.** Call `find_signal` — no arguments needed — to see which `signal_id`
  lines exist, how many entities each covers, and how fresh they are. This is free.
- **Verify a citation someone handed you.** Pass a `record_hash` to `verify_citation`.
  It returns whether that hash is a genuine Truth Bear record and, in plain language,
  exactly what the hash attests. This is free and needs nothing but the hash.
- **Get the price and payment details for a paid record.** Pass a `signal_id` and an `entity`
  to `get_official_record`. It returns the live x402 payment challenge — the network, asset,
  destination address, amount, and the URL to pay at.
  ⚠️ **This tool does not deliver paid data and does not take payment.** It hands the challenge
  back to you as data; paying is done by your own x402 client, outside Dify.

### Connection requirements

Outbound HTTPS to `https://api.truthbear.co` only. The base URL is compiled into the plugin and is
**not user-configurable**, so the plugin cannot be pointed at an arbitrary host.

## Credentials

None. The free tools work with no API key and no wallet.

## External paid service

Truth Bear is an external paid service. The free tools (verify_citation, find_signal) need no wallet and no API key. The paid tool returns an x402 payment challenge; this artifact surfaces that challenge as data and never holds, requests, or transacts a private key.

Current prices are always read live from the service — this plugin never stores a price.
See https://api.truthbear.co/manifest.

## Source

https://github.com/CHANGCHINFU/mcp-gauge
