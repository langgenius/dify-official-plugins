from .. import base
from dify_plugin.interfaces.trigger import Event


class DatabaseCreatedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.created"
