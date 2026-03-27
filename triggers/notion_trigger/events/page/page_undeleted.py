from .. import base
from dify_plugin.interfaces.trigger import Event


class PageUndeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.undeleted"
