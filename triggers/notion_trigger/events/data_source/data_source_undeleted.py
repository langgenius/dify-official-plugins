from .. import base
from dify_plugin.interfaces.trigger import Event


class DataSourceUndeletedEvent(base.NotionBaseEvent, Event):
    expected_type = "data_source.undeleted"
