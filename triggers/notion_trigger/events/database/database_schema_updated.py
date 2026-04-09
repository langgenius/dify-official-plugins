from .. import base
from dify_plugin.interfaces.trigger import Event


class DatabaseSchemaUpdatedEvent(base.NotionBaseEvent, Event):
    expected_type = "database.schema_updated"
