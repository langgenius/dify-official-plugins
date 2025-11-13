from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from examples.lark_trigger.events._shared import dispatch_single_event


class CalendarEventChangedV4Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle calendar event changes.

        This event is triggered when a calendar event is created, updated, or deleted.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_calendar_calendar_event_changed_v4,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "calendar_id": event_data.calendar_id if event_data.calendar_id else "",
            "event_id": event_data.calendar_event_id if event_data.calendar_event_id else "",
            "change_type": event_data.change_type if event_data.change_type else "",
        }

        # Add affected users
        if event_data.user_id_list:
            users_list = []
            for user in event_data.user_id_list:
                if user:
                    user_info = {}
                    if user.user_id:
                        user_info["user_id"] = user.user_id
                    if user.open_id:
                        user_info["open_id"] = user.open_id
                    if user.union_id:
                        user_info["union_id"] = user.union_id
                    users_list.append(user_info)

            variables_dict["affected_users"] = users_list
            variables_dict["affected_users_count"] = len(users_list)
        else:
            variables_dict["affected_users"] = []
            variables_dict["affected_users_count"] = 0

        # Add RSVP information
        if event_data.rsvp_infos:
            rsvp_list = []
            for rsvp in event_data.rsvp_infos:
                if rsvp:
                    rsvp_info = {
                        "rsvp_status": rsvp.rsvp_status if rsvp.rsvp_status else "",
                        "from_user_id": rsvp.from_user_id if rsvp.from_user_id else "",
                    }
                    rsvp_list.append(rsvp_info)

            variables_dict["rsvp_responses"] = rsvp_list
        else:
            variables_dict["rsvp_responses"] = []

        return Variables(
            variables=variables_dict,
        )
