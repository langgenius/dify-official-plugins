from .. import base
from dify_plugin.interfaces.trigger import Event


class DataSourceCreatedEvent(base.NotionBaseEvent, Event):
    expected_type = "data_source.created"
