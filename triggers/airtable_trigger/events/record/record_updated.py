from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import check_field_changed, check_field_contains, check_table_id


class RecordUpdatedEvent(Event):
    """Triggered when an Airtable record is updated."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        """Process Airtable webhook notification for record updates.
        
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
        changed_fields_filter = parameters.get("changed_fields")
        field_filter_name = parameters.get("field_filter_name")
        field_filter_keywords = parameters.get("field_filter_keywords")
        
        # In a real implementation, you would:
        # 1. Fetch the actual payloads from the API
        # 2. Parse the changeset to determine what changed
        # 3. Apply filters based on table_id and changed_fields
        # 4. Return the relevant record data
        
        # For now, return the notification payload
        return Variables(variables={
            "base_id": base_id,
            "webhook_id": webhook_id,
            "timestamp": payload.get("timestamp"),
            "notification": payload,
        })
