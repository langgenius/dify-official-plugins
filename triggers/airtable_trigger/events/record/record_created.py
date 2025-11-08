from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import check_field_contains, check_table_id


class RecordCreatedEvent(Event):
    """Triggered when a new Airtable record is created."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        """Process Airtable webhook notification and fetch actual payload data.
        
        Airtable sends a notification ping that doesn't contain the actual data.
        We need to fetch the payload from the API using the webhook ID.
        """
        # Get base_id and webhook_id from the notification payload
        payload = request.get_json()

        base_id = payload.get("base", {}).get("id")
        webhook_id = payload.get("webhook", {}).get("id")
        access_token = self.runtime.subscription.properties.get("access_token")
        # cursor = self.runtime.subscription.properties.get("cursor")
        cursor = self.runtime.session.storage.get("cursor") or 1

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        params = {
            "limit": 1,
            "cursor": cursor
        }
        response = httpx.get(
                    f"https://api.airtable.com/v0/bases/{base_id}/webhooks/{webhook_id}/payloads",
                    headers=headers,
                    params=params,
                    timeout=10
                )
        
        result = response.json()
        payloads = result.get("payloads", [])
        
        cursor = result.get("cursor")
        self.runtime.session.storage.set("cursor", cursor)
        # self.runtime.subscription.properties["cursor"] = cursor
        
        
        # Return the notification payload
        # In production, this should contain the actual record data fetched from the API
        return Variables(variables={
            "base_id": base_id,
            "webhook_id": webhook_id,
            "timestamp": payload.get("timestamp"),
            "notification": payloads,
        })
