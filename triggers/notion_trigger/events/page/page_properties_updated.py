from .. import base
from dify_plugin.interfaces.trigger import Event


class PagePropertiesUpdatedEvent(base.NotionBaseEvent, Event):
    expected_type = "page.properties_updated"
