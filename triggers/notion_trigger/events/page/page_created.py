from .. import base
from dify_plugin.interfaces.trigger import Event


class PageCreatedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.created"
