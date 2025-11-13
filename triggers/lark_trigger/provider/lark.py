import threading

import lark_oapi as lark
from lark_oapi.api.approval.v4 import P2ApprovalApprovalUpdatedV4
from lark_oapi.api.task.v1 import (
    P2TaskTaskCommentUpdatedV1,
    P2TaskTaskUpdatedV1,
)
from lark_oapi.api.calendar.v4 import (
    P2CalendarCalendarAclCreatedV4,
    P2CalendarCalendarAclDeletedV4,
    P2CalendarCalendarChangedV4,
    P2CalendarCalendarEventChangedV4,
)
from lark_oapi.api.contact.v3 import (
    P2ContactDepartmentCreatedV3,
    P2ContactDepartmentDeletedV3,
    P2ContactDepartmentUpdatedV3,
    P2ContactScopeUpdatedV3,
    P2ContactUserCreatedV3,
    P2ContactUserDeletedV3,
    P2ContactUserUpdatedV3,
)
from lark_oapi.api.drive.v1 import (
    P2DriveFileBitableFieldChangedV1,
    P2DriveFileBitableRecordChangedV1,
    P2DriveFileCreatedInFolderV1,
    P2DriveFileDeletedV1,
    P2DriveFileEditV1,
    P2DriveFilePermissionMemberAddedV1,
    P2DriveFilePermissionMemberRemovedV1,
    P2DriveFileReadV1,
    P2DriveFileTitleUpdatedV1,
    P2DriveFileTrashedV1,
)
from lark_oapi.api.im.v1 import (
    P2ImChatDisbandedV1,
    P2ImChatMemberBotAddedV1,
    P2ImChatMemberBotDeletedV1,
    P2ImChatMemberUserAddedV1,
    P2ImChatMemberUserDeletedV1,
    P2ImChatMemberUserWithdrawnV1,
    P2ImChatUpdatedV1,
    P2ImMessageMessageReadV1,
    P2ImMessageReactionCreatedV1,
    P2ImMessageReactionDeletedV1,
    P2ImMessageRecalledV1,
    P2ImMessageReceiveV1,
)
from lark_oapi.api.meeting_room.v1 import (
    P2MeetingRoomMeetingRoomCreatedV1,
    P2MeetingRoomMeetingRoomStatusChangedV1,
)
from lark_oapi.api.vc.v1 import (
    P2VcMeetingJoinMeetingV1,
    P2VcMeetingLeaveMeetingV1,
    P2VcMeetingMeetingEndedV1,
    P2VcMeetingMeetingStartedV1,
    P2VcMeetingRecordingEndedV1,
    P2VcMeetingRecordingReadyV1,
    P2VcMeetingRecordingStartedV1,
)
from lark_oapi.core.http import RawRequest
from werkzeug import Request, Response

from dify_plugin.entities.trigger import EventDispatch, Subscription
from dify_plugin.errors.trigger import TriggerDispatchError
from dify_plugin.interfaces.trigger import Trigger

"""
cache the response of the event, so that the response will not be cached by the browser
key: thread_id
value: events_to_dispatch
"""
response_cache_map: dict[int, list[str]] = {}


class LarkTrigger(Trigger):
    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        """
        Handle Lark event dispatch.
        """
        encrypt_key = subscription.properties.get("lark_encrypt_key")
        verification_token = subscription.properties.get("lark_verification_token")

        if not encrypt_key or not verification_token:
            raise TriggerDispatchError("Encrypt key or verification token not found")

        self.handler = (
            lark.EventDispatcherHandler.builder(
                encrypt_key,
                verification_token,
            )
            # IM Events
            .register_p2_im_message_receive_v1(
                self._handle_message_received_event,
            )
            .register_p2_im_chat_disbanded_v1(
                self._handle_chat_disbanded_event,
            )
            .register_p2_im_chat_updated_v1(
                self._handle_chat_updated_event,
            )
            .register_p2_im_chat_member_user_added_v1(
                self._handle_chat_member_user_added_event,
            )
            .register_p2_im_chat_member_user_deleted_v1(
                self._handle_chat_member_user_removed_event,
            )
            .register_p2_im_chat_member_user_withdrawn_v1(
                self._handle_chat_member_user_withdrawn_event,
            )
            .register_p2_im_chat_member_bot_added_v1(
                self._handle_chat_member_bot_added_event,
            )
            .register_p2_im_chat_member_bot_deleted_v1(
                self._handle_chat_member_bot_deleted_event,
            )
            .register_p2_im_message_reaction_created_v1(
                self._handle_message_reaction_added_event,
            )
            .register_p2_im_message_reaction_deleted_v1(
                self._handle_message_reaction_deleted_event,
            )
            .register_p2_im_message_recalled_v1(
                self._handle_message_recalled_event,
            )
            .register_p2_im_message_message_read_v1(
                self._handle_message_read_event,
            )
            # Calendar Events
            .register_p2_calendar_calendar_changed_v4(
                self._handle_calendar_changed_event,
            )
            .register_p2_calendar_calendar_event_changed_v4(
                self._handle_calendar_event_changed_event,
            )
            .register_p2_calendar_calendar_acl_created_v4(
                self._handle_calendar_acl_created_event,
            )
            .register_p2_calendar_calendar_acl_deleted_v4(
                self._handle_calendar_acl_deleted_event,
            )
            # Approval Events
            .register_p2_approval_approval_updated_v4(
                self._handle_approval_updated_event,
            )
            # Drive Events
            .register_p2_drive_file_created_in_folder_v1(
                self._handle_drive_file_created_event,
            )
            .register_p2_drive_file_deleted_v1(
                self._handle_drive_file_deleted_event,
            )
            .register_p2_drive_file_edit_v1(
                self._handle_drive_file_edited_event,
            )
            .register_p2_drive_file_permission_member_added_v1(
                self._handle_drive_permission_member_added_event,
            )
            .register_p2_drive_file_permission_member_removed_v1(
                self._handle_drive_permission_member_removed_event,
            )
            .register_p2_drive_file_read_v1(
                self._handle_drive_file_read_event,
            )
            .register_p2_drive_file_title_updated_v1(
                self._handle_drive_file_title_updated_event,
            )
            .register_p2_drive_file_trashed_v1(
                self._handle_drive_file_trashed_event,
            )
            .register_p2_drive_file_bitable_record_changed_v1(
                self._handle_drive_file_bitable_record_changed_event,
            )
            .register_p2_drive_file_bitable_field_changed_v1(
                self._handle_drive_file_bitable_field_changed_event,
            )
            # Task Events
            .register_p2_task_task_updated_v1(
                self._handle_task_updated_event,
            )
            .register_p2_task_task_comment_updated_v1(
                self._handle_task_comment_updated_event,
            )
            # Contact Events
            .register_p2_contact_user_created_v3(
                self._handle_contact_user_created_event,
            )
            .register_p2_contact_user_updated_v3(
                self._handle_contact_user_updated_event,
            )
            .register_p2_contact_user_deleted_v3(
                self._handle_contact_user_deleted_event,
            )
            .register_p2_contact_department_created_v3(
                self._handle_contact_department_created_event,
            )
            .register_p2_contact_department_updated_v3(
                self._handle_contact_department_updated_event,
            )
            .register_p2_contact_department_deleted_v3(
                self._handle_contact_department_deleted_event,
            )
            .register_p2_contact_scope_updated_v3(
                self._handle_contact_scope_updated_event,
            )
            # Meeting Room Events
            .register_p2_meeting_room_meeting_room_created_v1(
                self._handle_meeting_room_created_event,
            )
            .register_p2_meeting_room_meeting_room_status_changed_v1(
                self._handle_meeting_room_status_changed_event,
            )
            # VC Events
            .register_p2_vc_meeting_meeting_started_v1(
                self._handle_vc_meeting_started_event,
            )
            .register_p2_vc_meeting_meeting_ended_v1(
                self._handle_vc_meeting_ended_event,
            )
            .register_p2_vc_meeting_join_meeting_v1(
                self._handle_vc_join_meeting_event,
            )
            .register_p2_vc_meeting_leave_meeting_v1(
                self._handle_vc_leave_meeting_event,
            )
            .register_p2_vc_meeting_recording_started_v1(
                self._handle_vc_recording_started_event,
            )
            .register_p2_vc_meeting_recording_ended_v1(
                self._handle_vc_recording_ended_event,
            )
            .register_p2_vc_meeting_recording_ready_v1(
                self._handle_vc_recording_ready_event,
            )
            .build()
        )

        raw_request = RawRequest()
        raw_request.uri = request.url
        raw_request.headers = request.headers
        raw_request.body = request.get_data()

        events_to_dispatch = []
        response_cache_map[threading.get_ident()] = []

        try:
            """
            Do the event dispatch, and cache the response of the event
            """
            raw_response = self.handler.do(raw_request)
        finally:
            events_to_dispatch = response_cache_map.pop(threading.get_ident())

        return EventDispatch(
            response=Response(
                status=raw_response.status_code,
                headers=raw_response.headers,
                response=raw_response.content,
            ),
            events=events_to_dispatch,
        )

    def _handle_message_received_event(self, event: P2ImMessageReceiveV1) -> None:
        """
        Handle message received event.

        :param event: Message received event
        """
        response_cache_map[threading.get_ident()].append("message_receive_v1")

    def _handle_chat_disbanded_event(self, event: P2ImChatDisbandedV1) -> None:
        """
        Handle chat disbanded event.

        :param event: Chat disbanded event
        """
        response_cache_map[threading.get_ident()].append("chat_disbanded_v1")

    def _handle_chat_updated_event(self, event: P2ImChatUpdatedV1) -> None:
        """
        Handle chat updated event.

        :param event: Chat updated event
        """
        response_cache_map[threading.get_ident()].append("chat_updated_v1")

    def _handle_chat_member_user_added_event(self, event: P2ImChatMemberUserAddedV1) -> None:
        """
        Handle chat member user added event.

        :param event: Chat member user added event
        """
        response_cache_map[threading.get_ident()].append("chat_member_user_added_v1")

    def _handle_chat_member_user_removed_event(self, event: P2ImChatMemberUserDeletedV1) -> None:
        """
        Handle chat member user removed event.

        :param event: Chat member user removed event
        """
        response_cache_map[threading.get_ident()].append("chat_member_user_removed_v1")

    def _handle_message_reaction_added_event(self, event: P2ImMessageReactionCreatedV1) -> None:
        """
        Handle message reaction added event.

        :param event: Message reaction added event
        """
        response_cache_map[threading.get_ident()].append("message_reaction_added_v1")

    def _handle_message_recalled_event(self, event: P2ImMessageRecalledV1) -> None:
        """
        Handle message recalled event.

        :param event: Message recalled event
        """
        response_cache_map[threading.get_ident()].append("message_recalled_v1")

    def _handle_message_read_event(self, event: P2ImMessageMessageReadV1) -> None:
        """
        Handle message read event.

        :param event: Message read event
        """
        response_cache_map[threading.get_ident()].append("message_read_v1")

    def _handle_calendar_event_changed_event(self, event: P2CalendarCalendarEventChangedV4) -> None:
        """
        Handle calendar event changed.

        :param event: Calendar event changed event
        """
        response_cache_map[threading.get_ident()].append("event_changed_v4")

    def _handle_calendar_acl_created_event(self, event: P2CalendarCalendarAclCreatedV4) -> None:
        """Handle calendar ACL created events."""

        response_cache_map[threading.get_ident()].append("calendar_acl_created_v4")

    def _handle_calendar_acl_deleted_event(self, event: P2CalendarCalendarAclDeletedV4) -> None:
        """Handle calendar ACL deleted events."""

        response_cache_map[threading.get_ident()].append("calendar_acl_deleted_v4")

    def _handle_approval_updated_event(self, event: P2ApprovalApprovalUpdatedV4) -> None:
        """
        Handle approval updated event.

        :param event: Approval updated event
        """
        response_cache_map[threading.get_ident()].append("approval_updated_v4")

    def _handle_drive_file_created_event(self, event: P2DriveFileCreatedInFolderV1) -> None:
        """
        Handle drive file created event.

        :param event: Drive file created event
        """
        response_cache_map[threading.get_ident()].append("file_created_v1")

    def _handle_drive_file_deleted_event(self, event: P2DriveFileDeletedV1) -> None:
        """Handle drive file deleted events."""

        response_cache_map[threading.get_ident()].append("file_deleted_v1")

    def _handle_drive_file_edited_event(self, event: P2DriveFileEditV1) -> None:
        """Handle drive file edited events."""

        response_cache_map[threading.get_ident()].append("file_edit_v1")

    def _handle_drive_permission_member_added_event(
        self, event: P2DriveFilePermissionMemberAddedV1
    ) -> None:
        """Handle drive file permission member added events."""

        response_cache_map[threading.get_ident()].append("file_permission_member_added_v1")

    def _handle_drive_permission_member_removed_event(
        self, event: P2DriveFilePermissionMemberRemovedV1
    ) -> None:
        """Handle drive file permission member removed events."""

        response_cache_map[threading.get_ident()].append("file_permission_member_removed_v1")

    def _handle_drive_file_trashed_event(self, event: P2DriveFileTrashedV1) -> None:
        """Handle drive file trashed events."""

        response_cache_map[threading.get_ident()].append("file_trashed_v1")

    def _handle_contact_user_created_event(self, event: P2ContactUserCreatedV3) -> None:
        """
        Handle contact user created event.

        :param event: Contact user created event
        """
        response_cache_map[threading.get_ident()].append("user_created_v3")

    def _handle_contact_user_updated_event(self, event: P2ContactUserUpdatedV3) -> None:
        """Handle contact user updated events."""

        response_cache_map[threading.get_ident()].append("user_updated_v3")

    def _handle_contact_user_deleted_event(self, event: P2ContactUserDeletedV3) -> None:
        """Handle contact user deleted events."""

        response_cache_map[threading.get_ident()].append("user_deleted_v3")

    def _handle_contact_department_created_event(self, event: P2ContactDepartmentCreatedV3) -> None:
        """
        Handle contact department created event.

        :param event: Contact department created event
        """
        response_cache_map[threading.get_ident()].append("department_created_v3")

    def _handle_contact_department_updated_event(self, event: P2ContactDepartmentUpdatedV3) -> None:
        """Handle contact department updated events."""

        response_cache_map[threading.get_ident()].append("department_updated_v3")

    def _handle_contact_department_deleted_event(self, event: P2ContactDepartmentDeletedV3) -> None:
        """Handle contact department deleted events."""

        response_cache_map[threading.get_ident()].append("department_deleted_v3")

    def _handle_chat_member_user_withdrawn_event(self, event: P2ImChatMemberUserWithdrawnV1) -> None:
        """
        Handle chat member user withdrawn event.

        :param event: Chat member user withdrawn event
        """
        response_cache_map[threading.get_ident()].append("chat_member_user_withdrawn_v1")

    def _handle_chat_member_bot_added_event(self, event: P2ImChatMemberBotAddedV1) -> None:
        """
        Handle chat member bot added event.

        :param event: Chat member bot added event
        """
        response_cache_map[threading.get_ident()].append("chat_member_bot_added_v1")

    def _handle_chat_member_bot_deleted_event(self, event: P2ImChatMemberBotDeletedV1) -> None:
        """
        Handle chat member bot deleted event.

        :param event: Chat member bot deleted event
        """
        response_cache_map[threading.get_ident()].append("chat_member_bot_deleted_v1")

    def _handle_message_reaction_deleted_event(self, event: P2ImMessageReactionDeletedV1) -> None:
        """
        Handle message reaction deleted event.

        :param event: Message reaction deleted event
        """
        response_cache_map[threading.get_ident()].append("message_reaction_deleted_v1")

    def _handle_drive_file_read_event(self, event: P2DriveFileReadV1) -> None:
        """
        Handle drive file read event.

        :param event: Drive file read event
        """
        response_cache_map[threading.get_ident()].append("file_read_v1")

    def _handle_drive_file_title_updated_event(self, event: P2DriveFileTitleUpdatedV1) -> None:
        """
        Handle drive file title updated event.

        :param event: Drive file title updated event
        """
        response_cache_map[threading.get_ident()].append("file_title_updated_v1")

    def _handle_calendar_changed_event(self, event: P2CalendarCalendarChangedV4) -> None:
        """
        Handle calendar changed event.

        :param event: Calendar changed event
        """
        response_cache_map[threading.get_ident()].append("calendar_changed_v4")

    def _handle_contact_scope_updated_event(self, event: P2ContactScopeUpdatedV3) -> None:
        """
        Handle contact scope updated event.

        :param event: Contact scope updated event
        """
        response_cache_map[threading.get_ident()].append("scope_updated_v3")

    def _handle_drive_file_bitable_record_changed_event(self, event: P2DriveFileBitableRecordChangedV1) -> None:
        """
        Handle drive file bitable record changed event.

        :param event: Bitable record changed event
        """
        response_cache_map[threading.get_ident()].append("file_bitable_record_changed_v1")

    def _handle_drive_file_bitable_field_changed_event(self, event: P2DriveFileBitableFieldChangedV1) -> None:
        """
        Handle drive file bitable field changed event.

        :param event: Bitable field changed event
        """
        response_cache_map[threading.get_ident()].append("file_bitable_field_changed_v1")

    def _handle_task_updated_event(self, event: P2TaskTaskUpdatedV1) -> None:
        """
        Handle task updated event.

        :param event: Task updated event
        """
        response_cache_map[threading.get_ident()].append("task_updated_v1")

    def _handle_task_comment_updated_event(self, event: P2TaskTaskCommentUpdatedV1) -> None:
        """
        Handle task comment updated event.

        :param event: Task comment updated event
        """
        response_cache_map[threading.get_ident()].append("task_comment_updated_v1")

    def _handle_meeting_room_created_event(self, event: P2MeetingRoomMeetingRoomCreatedV1) -> None:
        """
        Handle meeting room created event.

        :param event: Meeting room created event
        """
        response_cache_map[threading.get_ident()].append("meeting_room_created_v1")

    def _handle_meeting_room_status_changed_event(self, event: P2MeetingRoomMeetingRoomStatusChangedV1) -> None:
        """
        Handle meeting room status changed event.

        :param event: Meeting room status changed event
        """
        response_cache_map[threading.get_ident()].append("meeting_room_status_changed_v1")

    def _handle_vc_meeting_started_event(self, event: P2VcMeetingMeetingStartedV1) -> None:
        """
        Handle VC meeting started event.

        :param event: VC meeting started event
        """
        response_cache_map[threading.get_ident()].append("meeting_started_v1")

    def _handle_vc_meeting_ended_event(self, event: P2VcMeetingMeetingEndedV1) -> None:
        """
        Handle VC meeting ended event.

        :param event: VC meeting ended event
        """
        response_cache_map[threading.get_ident()].append("meeting_ended_v1")

    def _handle_vc_recording_ready_event(self, event: P2VcMeetingRecordingReadyV1) -> None:
        """
        Handle VC recording ready event.

        :param event: VC recording ready event
        """
        response_cache_map[threading.get_ident()].append("recording_ready_v1")

    def _handle_vc_join_meeting_event(self, event: P2VcMeetingJoinMeetingV1) -> None:
        """
        Handle VC join meeting event.

        :param event: VC join meeting event
        """
        response_cache_map[threading.get_ident()].append("join_meeting_v1")

    def _handle_vc_leave_meeting_event(self, event: P2VcMeetingLeaveMeetingV1) -> None:
        """
        Handle VC leave meeting event.

        :param event: VC leave meeting event
        """
        response_cache_map[threading.get_ident()].append("leave_meeting_v1")

    def _handle_vc_recording_started_event(self, event: P2VcMeetingRecordingStartedV1) -> None:
        """
        Handle VC recording started event.

        :param event: VC recording started event
        """
        response_cache_map[threading.get_ident()].append("recording_started_v1")

    def _handle_vc_recording_ended_event(self, event: P2VcMeetingRecordingEndedV1) -> None:
        """
        Handle VC recording ended event.

        :param event: VC recording ended event
        """
        response_cache_map[threading.get_ident()].append("recording_ended_v1")
