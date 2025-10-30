from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GridMigrationStartedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `grid.migration.started`."""

    EVENT_KEY = "grid_migration_started"
