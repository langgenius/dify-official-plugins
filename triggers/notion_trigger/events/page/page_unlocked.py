from .. import base
from dify_plugin.interfaces.trigger import Event


class PageUnlockedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.unlocked"
