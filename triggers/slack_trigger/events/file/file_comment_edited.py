from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileCommentEditedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.comment.edited`."""

    EVENT_KEY = "file_comment_edited"
