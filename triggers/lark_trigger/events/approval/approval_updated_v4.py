from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event


from examples.lark_trigger.events._shared import dispatch_single_event


class ApprovalUpdatedV4Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle approval process updates.

        This event is triggered when an approval request status changes.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_approval_approval_updated_v4,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        approval_data = event_data.object
        if approval_data is None:
            raise ValueError("approval_data is None")

        # Build variables dictionary
        variables_dict = {
            "approval_code": approval_data.approval_code if approval_data.approval_code else "",
            "approval_id": approval_data.approval_id if approval_data.approval_id else "",
            "timestamp": approval_data.timestamp if approval_data.timestamp else "",
            "version_id": approval_data.version_id if approval_data.version_id else "",
            "form_definition_id": approval_data.form_definition_id if approval_data.form_definition_id else "",
            "widget_group_type": approval_data.widget_group_type if approval_data.widget_group_type is not None else 0,
            "process_obj": approval_data.process_obj if approval_data.process_obj else "",
            "extra": approval_data.extra if approval_data.extra else "",
        }

        return Variables(
            variables=variables_dict,
        )
