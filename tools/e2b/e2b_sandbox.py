from typing import Any

from e2b_code_interpreter import Sandbox


def get_sandbox(
    *,
    api_key: str,
    timeout: int,
    domain: str | None = None,
    sandbox_id: str | None = None,
) -> Sandbox:
    opts: dict[str, Any] = {"api_key": api_key}
    if domain:
        opts["domain"] = domain
    if sandbox_id:
        return Sandbox.connect(sandbox_id=sandbox_id, timeout=timeout, **opts)
    return Sandbox.create(timeout=timeout, **opts)
