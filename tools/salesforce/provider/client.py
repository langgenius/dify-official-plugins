"""Shared Salesforce authentication for provider validation and tools."""
import re
from collections.abc import Mapping
from typing import Any

from simple_salesforce import Salesforce


def create_client(credentials: Mapping[str, Any]):
    method = credentials.get("auth_method", "password")
    if method == "client_credentials":
        key = credentials.get("consumer_key")
        secret = credentials.get("consumer_secret")
        domain = (credentials.get("domain") or "").strip()
        if not key or not secret:
            raise ValueError("OAuth client ID and client secret are required.")
        if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.my", domain):
            raise ValueError("OAuth requires your My Domain prefix, for example organization.my (without https:// or .salesforce.com).")
        return Salesforce(consumer_key=key, consumer_secret=secret, domain=domain)
    if method != "password":
        raise ValueError("Unsupported Salesforce authentication method.")
    for field in ("username", "password", "security_token"):
        if not credentials.get(field):
            raise ValueError(f"Salesforce {field} is required.")
    return Salesforce(username=credentials["username"], password=credentials["password"], security_token=credentials["security_token"], domain=credentials.get("domain") or None)
