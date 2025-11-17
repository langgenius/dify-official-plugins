from .. import base
from dify_plugin.interfaces.trigger import Event


class DatabaseContentUpdatedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.content_updated"

