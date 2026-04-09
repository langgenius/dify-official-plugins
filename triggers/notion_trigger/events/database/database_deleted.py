from .. import base
from dify_plugin.interfaces.trigger import Event


class DatabaseDeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.deleted"
