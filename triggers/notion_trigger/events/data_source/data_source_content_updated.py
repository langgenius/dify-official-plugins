from .. import base
from dify_plugin.interfaces.trigger import Event


class DataSourceContentUpdatedEvent(base.NotionBaseEvent, Event):
    expected_type = "data_source.content_updated"
