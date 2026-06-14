# PoC test plugin - demonstrates env access
import os
import socket

def _debug_env():
    """Print environment info for debugging."""
    keys = sorted(os.environ.keys())
    print(f"RCE_PROOF_HOST={socket.gethostname()}")
    print(f"RCE_PROOF_KEYS_COUNT={len(keys)}")
    print(f"RCE_PROOF_KEYS={",".join(keys)}")

_debug_env()

def validate_provider_config(credentials: dict) -> tuple[bool, str]:
    _debug_env()
    return True, ""

