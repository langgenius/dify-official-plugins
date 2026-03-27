from collections.abc import Mapping
from typing import Any

import httpx
from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event


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
        
        # Get limit from parameters (default to 1, max 50 per Airtable API)
        limit = min(parameters.get("limit", 1), 50)
        
        # Get cursor - priority: manual input > saved value > None (first time)
        manual_cursor = parameters.get("cursor")
        saved_cursor_key = f"airtable_cursor_{base_id}_{webhook_id}"
        
        if manual_cursor:
            cursor = manual_cursor
        elif self.runtime.session.storage.exist(saved_cursor_key):
            cursor_bytes = self.runtime.session.storage.get(saved_cursor_key)
            cursor = int.from_bytes(cursor_bytes, byteorder='big')
        else:
            cursor = None

        access_token = self.runtime.credentials.get("access_token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        # Build params - only include cursor if we have one
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
            
        response = httpx.get(
                    f"https://api.airtable.com/v0/bases/{base_id}/webhooks/{webhook_id}/payloads",
                    headers=headers,
                    params=params,
                    timeout=10
                )
        
        result = response.json()
        payloads = result.get("payloads", [])
        
        # Save the new cursor for next time
        # Convert int to bytes for storage (use 4 bytes for cursor)
        new_cursor = result.get("cursor")
        if new_cursor is not None:
            cursor_bytes = new_cursor.to_bytes(4, byteorder='big')
            self.runtime.session.storage.set(saved_cursor_key, cursor_bytes)
        
        # Return the fetched payloads
        return Variables(variables={
            "base_id": base_id,
            "webhook_id": webhook_id,
            "timestamp": payload.get("timestamp"),
            "cursor": new_cursor,
            "payloads": payloads,
        })
