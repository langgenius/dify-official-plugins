from .. import base
from dify_plugin.interfaces.trigger import Event


class PageMovedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.moved"
