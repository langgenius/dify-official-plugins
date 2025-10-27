from .. import base
from dify_plugin.interfaces.trigger import Event


class CommentDeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "comment.deleted"
