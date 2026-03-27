from .. import base
from dify_plugin.interfaces.trigger import Event


class DatabaseUndeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.undeleted"
