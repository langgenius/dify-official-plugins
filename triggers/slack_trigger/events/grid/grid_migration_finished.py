from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GridMigrationFinishedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `grid.migration.finished`."""

    EVENT_KEY = "grid_migration_finished"
