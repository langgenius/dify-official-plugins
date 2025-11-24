from .. import base
from dify_plugin.interfaces.trigger import Event


class PageDeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.deleted"
