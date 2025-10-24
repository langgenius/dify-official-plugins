import re
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class EmailReceivedEvent(Event):
    """
    Outlook Email Received Event

    This event transforms Outlook email received webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    The payload includes an 'email' object with the email details.
    """

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        """
        Transform Outlook email received webhook event into structured Variables
        """
        sender_email_address = parameters.get("sender_email_address")

        if sender_email_address:
            allowed_addresses = [address.strip() for address in sender_email_address.split(",") if address.strip()]
            if allowed_addresses:
                if payload.get("sender").get("emailAddress").get("address") not in allowed_addresses:
                    raise EventIgnoreError()

        return Variables(variables={**payload})
