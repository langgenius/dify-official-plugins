from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileCommentDeletedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.comment.deleted`."""

    EVENT_KEY = "file_comment_deleted"
