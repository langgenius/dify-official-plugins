from .. import base
from dify_plugin.interfaces.trigger import Event


class CommentUpdatedEvent(base.NotionBaseEvent, Event):
    expected_type = "comment.updated"
