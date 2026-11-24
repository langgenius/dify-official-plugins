# Pocket RPC

Live on-chain data for Dify agents, served over Pocket Network's free public RPC endpoints. No API key, no payment, no account.

## What it provides

Pocket Network is a decentralized network of independent node operators that serve data services. Its free public RPC endpoints answer standard Ethereum JSON-RPC calls for dozens of chains, with no key and no cost. This plugin exposes three read-only tools over those endpoints:

- **Pocket Block Number**: the current block number of a chain.
- **Pocket Balance**: the balance of an address on a chain, in wei and in the chain's native token.
- **Pocket Transaction**: a transaction by hash on a chain, with sender, recipient, value, and block number.

Supported chains, all verified live:

| Chain | Endpoint | Chain ID |
| --- | --- | --- |
| Ethereum | https://eth.api.pocket.network | 1 |
| Base | https://base.api.pocket.network | 8453 |
| Polygon | https://poly.api.pocket.network | 137 |
| Arbitrum One | https://arb-one.api.pocket.network | 42161 |
| Optimism | https://op.api.pocket.network | 10 |
| Celo | https://celo.api.pocket.network | 42220 |

## How to configure it

There is nothing to configure. Install this plugin in Dify and use the tools. No API key, no wallet, no payment, no account. Saving the provider runs a free live check (it reads the current Ethereum block number) and costs nothing.

## Expected outputs

All examples below are real outputs captured live from Pocket's free endpoints on 2026-11-24. The full verification record is in the PR evidence.

### Pocket Block Number

Input: `chain` (required, one of ethereum, base, polygon, arbitrum-one, optimism, celo; default ethereum).

Output: a JSON message plus a formatted text message. The JSON has the shape:

```json
{
  "chain": "ethereum",
  "chain_id": 1,
  "block_number": 26483601,
  "block_number_hex": "0x1941b91"
}
```

### Pocket Balance

Input: `chain` (required), `address` (required, a 0x address with 40 hex characters).

Output: a JSON message plus a formatted text message. Real example, vitalik.eth on Ethereum:

```json
{
  "chain": "ethereum",
  "chain_id": 1,
  "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
  "balance_wei": 571415652438114252915592,
  "balance_wei_hex": "0x7900812cb295fff48388",
  "balance_native": 571415.6524381143,
  "native_symbol": "ETH"
}
```

### Pocket Transaction

Input: `chain` (required), `tx_hash` (required, a 0x hash with 64 hex characters).

Output: a JSON message plus a formatted text message. Real example, an Ethereum transaction:

```json
{
  "chain": "ethereum",
  "chain_id": 1,
  "transaction": {
    "blockNumber": "0x1941b92",
    "from": "0x46565eedb0bb948ae787dd105cce300f736da28e",
    "to": "0x00000000005ad9ce1f5035fd62ca96cef16adaaf",
    "hash": "0x1b8843678cbaa88d61c8d3a0a556cd2accf79507cd728d832b0259e0dff0c45e",
    "value": "0x0"
  }
}
```

If no transaction exists with the given hash, the tool says so instead of returning an empty result.

## Errors

- An invalid address or transaction hash is rejected before any call is made, with a message saying what is wrong.
- An unsupported chain is rejected with the list of supported chains.
- If a Pocket endpoint is unreachable or returns an error, the tool reports that it could not connect or what the endpoint said. These are read-only calls, so nothing is ever signed or sent.

## Links

- Pocket Network docs: https://docs.pocket.network/
- Agentic Portal services: https://agent.pocket.network/services
- Pocket Network: https://pocket.network/
