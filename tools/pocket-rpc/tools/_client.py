"""Pocket Network free public JSON-RPC client.

Calls Pocket's free public RPC endpoints, for example
https://eth.api.pocket.network. No API key, no payment, no account.
Read-only calls only.
"""

import re

import requests

# Chain slug -> (free public endpoint, chain id). Every endpoint below was
# verified live to answer eth_chainId with the matching id.
CHAINS = {
    "ethereum": ("https://eth.api.pocket.network", 1),
    "base": ("https://base.api.pocket.network", 8453),
    "polygon": ("https://poly.api.pocket.network", 137),
    "arbitrum-one": ("https://arb-one.api.pocket.network", 42161),
    "optimism": ("https://op.api.pocket.network", 10),
    "celo": ("https://celo.api.pocket.network", 42220),
}

# Chain slug -> native token symbol, for display only.
NATIVE_SYMBOL = {
    "ethereum": "ETH",
    "base": "ETH",
    "polygon": "POL",
    "arbitrum-one": "ETH",
    "optimism": "ETH",
    "celo": "CELO",
}

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class PocketRPCError(Exception):
    """Raised when a Pocket RPC call fails."""


class PocketRPCClient:
    """Thin client over Pocket's free public JSON-RPC endpoints."""

    def __init__(self, timeout: int = 15):
        self._session = requests.Session()
        self._timeout = timeout

    def _endpoint(self, chain: str) -> tuple[str, int]:
        entry = CHAINS.get(chain)
        if entry is None:
            raise PocketRPCError(
                f"Unsupported chain '{chain}'. Supported chains: "
                + ", ".join(sorted(CHAINS))
            )
        return entry

    def _call(self, chain: str, method: str, params: list) -> object:
        url, expected_chain_id = self._endpoint(chain)
        try:
            response = self._session.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise PocketRPCError(
                f"Could not reach Pocket's {chain} endpoint ({url}): {e}"
            ) from None
        try:
            payload = response.json()
        except ValueError:
            raise PocketRPCError(
                f"Pocket's {chain} endpoint returned a non-JSON response "
                f"(HTTP {response.status_code})."
            ) from None
        if "error" in payload:
            error = payload["error"]
            raise PocketRPCError(
                f"Pocket's {chain} endpoint returned an error: "
                f"{error.get('message', error)}"
            )
        if "result" not in payload:
            raise PocketRPCError(
                f"Pocket's {chain} endpoint returned an unexpected response."
            )
        return payload["result"]

    def chain_id(self, chain: str) -> int:
        """Return the chain id the endpoint reports, as an integer."""
        result = self._call(chain, "eth_chainId", [])
        return int(result, 16)

    def block_number(self, chain: str) -> int:
        """Return the current block number as an integer."""
        result = self._call(chain, "eth_blockNumber", [])
        return int(result, 16)

    def balance(self, chain: str, address: str) -> int:
        """Return the balance of an address in wei as an integer."""
        if not _ADDRESS_RE.match(address):
            raise PocketRPCError(
                "Invalid address. Expected a 0x address with 40 hex characters."
            )
        result = self._call(chain, "eth_getBalance", [address, "latest"])
        return int(result, 16)

    def transaction(self, chain: str, tx_hash: str) -> dict | None:
        """Return a transaction by hash, or None if it is not found."""
        if not _TX_HASH_RE.match(tx_hash):
            raise PocketRPCError(
                "Invalid transaction hash. Expected a 0x hash with 64 hex characters."
            )
        result = self._call(chain, "eth_getTransactionByHash", [tx_hash])
        if result is None:
            return None
        if not isinstance(result, dict):
            raise PocketRPCError(
                "Pocket's endpoint returned an unexpected transaction response."
            )
        return result
