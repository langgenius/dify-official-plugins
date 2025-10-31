from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class TaskCommentUpdatedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle task comment updated event.
        
        This event is triggered when a comment on a task is added or updated.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_task_task_comment_updated_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "task_id": event_data.task_id if event_data.task_id else "",
            "comment_id": event_data.comment_id if event_data.comment_id else "",
            "parent_id": event_data.parent_id if event_data.parent_id else "",
            "obj_type": event_data.obj_type if event_data.obj_type else "",
        }

        return Variables(
            variables=variables_dict,
        )