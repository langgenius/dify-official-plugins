from .. import base
from dify_plugin.interfaces.trigger import Event


class PageLockedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.locked"
