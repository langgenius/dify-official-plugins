"""
Pytest configuration and fixtures for OpenAI tests.
"""
import pytest
from tests.models.__mockserver.openai import OpenAIMockServer
from dify_plugin.integration.run import PluginRunner
from dify_plugin.config.integration_config import IntegrationConfig


@pytest.fixture(scope="module")
def mock_server():
    """
    Module-scoped fixture that starts the mock server once for all tests in the module.
    This significantly speeds up test execution by avoiding repeated server startup/shutdown.
    """
    print("\n🚀 Starting OpenAI Mock Server (once per module)...")
    server = OpenAIMockServer()
    print(f"✅ Mock Server started on port {server.process.pid}")
    yield server
    print("\n🛑 Shutting down OpenAI Mock Server...")
    server.process.terminate()
    print("✅ Mock Server terminated")


@pytest.fixture(scope="module")
def plugin_runner():
    """
    Module-scoped fixture that creates a PluginRunner once for all tests.
    This dramatically speeds up tests by avoiding repeated plugin process startup.
    """
    print("\n🔌 Starting PluginRunner (once per module)...")
    with PluginRunner(
        config=IntegrationConfig(),
        plugin_package_path="models/openai",
    ) as runner:
        print("✅ PluginRunner started")
        yield runner
        print("\n🔌 Shutting down PluginRunner...")
    print("✅ PluginRunner terminated")

