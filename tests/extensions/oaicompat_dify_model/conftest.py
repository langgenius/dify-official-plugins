"""
Pytest configuration and fixtures for oaicompat_dify_model tests.
"""
import pytest
from dify_plugin.integration.run import PluginRunner
from dify_plugin.config.integration_config import IntegrationConfig


@pytest.fixture(scope="module")
def plugin_runner():
    """
    Module-scoped fixture that creates a PluginRunner once for all tests.
    """
    print("\n🔌 Starting PluginRunner (once per module)...")
    with PluginRunner(
        config=IntegrationConfig(),
        plugin_package_path="extensions/oaicompat_dify_model",
    ) as runner:
        print("✅ PluginRunner started")
        yield runner
        print("\n🔌 Shutting down PluginRunner...")
    print("✅ PluginRunner terminated")
