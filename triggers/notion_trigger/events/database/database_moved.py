from .. import base
from dify_plugin.interfaces.trigger import Event


class DatabaseMovedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.moved"
