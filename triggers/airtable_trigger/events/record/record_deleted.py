from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import check_table_id


class RecordDeletedEvent(Event):
    """Triggered when an Airtable record is deleted."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        """Process Airtable webhook notification for record deletions.
        
        Airtable sends a notification ping that doesn't contain the actual data.
        We need to fetch the payload from the API using the webhook ID.
        """
        # Get base_id and webhook_id from the notification payload
        base_info = payload.get("base", {})
        webhook_info = payload.get("webhook", {})
        
        base_id = base_info.get("id")
        webhook_id = webhook_info.get("id")
        
        if not base_id or not webhook_id:
            raise ValueError("Invalid webhook notification: missing base_id or webhook_id")

        # Apply filters based on parameters
        table_id_filter = parameters.get("table_id")
        
        # In a real implementation, you would:
        # 1. Fetch the actual payloads from the API
        # 2. Parse the changeset to find deleted records
        # 3. Apply filters based on table_id
        # 4. Return the relevant deleted record information
        
        # For now, return the notification payload
        return Variables(variables={
            "base_id": base_id,
            "webhook_id": webhook_id,
            "timestamp": payload.get("timestamp"),
            "notification": payload,
        })
