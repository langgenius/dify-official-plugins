from .. import base
from dify_plugin.interfaces.trigger import Event


class DataSourceDeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "data_source.deleted"
