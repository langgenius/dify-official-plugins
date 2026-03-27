from .. import base
from dify_plugin.interfaces.trigger import Event


class CommentCreatedEvent(base.NotionBaseEvent, Event):
    expected_type = "comment.created"
