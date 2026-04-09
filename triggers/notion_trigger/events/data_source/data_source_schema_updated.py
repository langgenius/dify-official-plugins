from .. import base
from dify_plugin.interfaces.trigger import Event


class DataSourceSchemaUpdatedEvent(base.NotionBaseEvent, Event):
    expected_type = "data_source.schema_updated"
