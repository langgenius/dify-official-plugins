import json
import os
from typing import Any, Dict, Optional

import requests


def _mask(value: Optional[str], keep: int = 3) -> str:
    if not value:
        return ""
    v = str(value)
    if len(v) <= keep * 2:
        return "*" * len(v)
    return f"{v[:keep]}...{v[-keep:]}"


class HapRequest:
    """
    HTTP wrapper for HAP v3 OpenAPI.

    - Headers:
      Content-Type: application/json
      HAP-Appkey: {appkey}
      HAP-Sign: {sign}
    - Base URL normalization:
      - default https://api2.mingdao.com
      - remove trailing '/'
      - join with path (which should start with '/v3/...')
    - Error handling:
      - HTTP non-2xx -> raise Exception with status & snippet
      - JSON parse error -> raise Exception
      - Business layer is returned as-is and should be checked by caller
    - Debug log:
      - enable via env HAP_DEBUG=true
      - sensitive fields are masked
    """

    def __init__(self, credentials: Dict[str, Any]) -> None:
        self.appkey = credentials.get("appkey")
        self.sign = credentials.get("sign")
        
        if not self.appkey or not self.sign:
            raise ValueError("appkey and sign are required")
        
        # Get api_base from credentials, default to mingdao.com
        api_base = credentials.get("api_base")
        self.api_base = self._normalize_base(api_base or "https://api2.mingdao.com")

    @staticmethod
    def _normalize_base(api_base: str) -> str:
        base = api_base.strip()
        if not (base.startswith("http://") or base.startswith("https://")):
            raise ValueError("api_base must start with http:// or https://")
        return base.rstrip("/")

    def headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "HAP-Appkey": self.appkey,
            "HAP-Sign": self.sign,
            "User-Agent": "Dify-HAP-Plugin",
        }

    def build_url(self, path: str) -> str:
        p = path.strip()
        if not p.startswith("/"):
            p = "/" + p
        return f"{self.api_base}{p}"

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        url = self.build_url(path)
        headers = self.headers()
        debug = os.getenv("HAP_DEBUG", "").lower() in ("1", "true", "yes", "on")

        # Prepare masked debug info
        if debug:
            masked_headers = dict(headers)
            masked_headers["HAP-Appkey"] = _mask(headers.get("HAP-Appkey"))
            masked_headers["HAP-Sign"] = _mask(headers.get("HAP-Sign"))
            print(
                f"[HAP DEBUG] {method.upper()} {url}\n"
                f"Headers: {json.dumps(masked_headers, ensure_ascii=False)}\n"
                f"Params: {json.dumps(params or {}, ensure_ascii=False)}\n"
                f"Body: {json.dumps(json_body or {}, ensure_ascii=False)}"
            )

        try:
            timeout = timeout_seconds or 120.0
            resp = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=timeout,
            )
        except Exception as e:
            raise Exception(f"Network request failed: {e}")

        if resp.status_code < 200 or resp.status_code >= 300:
            text = resp.text or ""
            snippet = text[:4096]
            raise Exception(f"HTTP {resp.status_code}: {snippet}")

        try:
            data = resp.json()
        except Exception:
            snippet = (resp.text or "")[:4096]
            raise Exception(f"Failed to parse response JSON: {snippet}")

        if debug:
            # Mask possible sensitive values in response if needed
            try:
                safe_data = json.loads(json.dumps(data))  # deep copy
                # Do not print headers here; only body; errorMsg may contain details already
                print(f"[HAP DEBUG] Response: {json.dumps(safe_data, ensure_ascii=False)[:4096]}")
            except Exception:
                pass

        # Return raw parsed JSON; caller should check success/errorCode/errorMsg/data
        return data

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params, json_body=None)

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("POST", path, params=params, json_body=json_body)

    def put(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("PUT", path, params=params, json_body=json_body)

    def patch(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("PATCH", path, params=params, json_body=json_body)

    def delete(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("DELETE", path, params=params, json_body=json_body)
