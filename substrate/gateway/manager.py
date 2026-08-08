"""Gateway plugin manager — discovery, lifecycle, and registry management."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from .models import GatewayPlugin, PluginMetadata

logger = logging.getLogger(__name__)


class GatewayManager:
    """Manages gateway plugins: discovery, initialization, and lifecycle."""
    
    def __init__(self, plugins_dir: Path | None = None):
        """Initialize the gateway manager.
        
        Args:
            plugins_dir: Directory containing plugin modules. Defaults to
                substrate/gateway/plugins/
        """
        self.plugins_dir = plugins_dir or Path(__file__).parent / "plugins"
        self._registry: dict[str, PluginMetadata] = {}
        self._initialized = False
    
    def discover_plugins(self) -> list[str]:
        """Discover available plugins in the plugins directory.
        
        Returns:
            List of discovered plugin module names.
        """
        discovered = []
        
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory not found: {self.plugins_dir}")
            return discovered
        
        for path in self.plugins_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            
            module_name = path.stem
            discovered.append(module_name)
            logger.info(f"Discovered plugin: {module_name}")
        
        return discovered
    
    def load_plugin(self, module_name: str, config: dict[str, Any]) -> bool:
        """Load and initialize a plugin.
        
        Args:
            module_name: Name of the plugin module.
            config: Plugin configuration.
            
        Returns:
            True if plugin loaded successfully, False otherwise.
        """
        try:
            # Import the plugin module
            module = importlib.import_module(f"substrate.gateway.plugins.{module_name}")
            
            # Check for register_plugin function
            if not hasattr(module, "register_plugin"):
                logger.error(f"Plugin {module_name} missing register_plugin() function")
                return False
            
            # Create plugin instance
            plugin = module.register_plugin()
            
            # Validate protocol compliance
            if not isinstance(plugin, GatewayPlugin):
                logger.error(f"Plugin {module_name} does not implement GatewayPlugin protocol")
                return False
            
            # Initialize plugin
            plugin.initialize(config)
            
            # Create metadata
            metadata = PluginMetadata(
                id=plugin.service_id,
                name=plugin.service_name,
                version=plugin.version,
                enabled=True,
                config=config,
                instance=plugin,
                webhook_url=f"/gateway/{plugin.service_id}/webhook",
                capabilities=self._get_capabilities(plugin),
                initialized=True
            )
            
            # Register plugin
            self._registry[plugin.service_id] = metadata
            logger.info(f"Loaded plugin: {plugin.service_name} v{plugin.version}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load plugin {module_name}: {e}")
            
            # Register with error state
            metadata = PluginMetadata(
                id=module_name,
                name=module_name,
                version="unknown",
                enabled=False,
                config=config,
                instance=None,
                webhook_url=f"/gateway/{module_name}/webhook",
                capabilities=[],
                initialized=False,
                error=str(e)
            )
            self._registry[module_name] = metadata
            
            return False
    
    def _get_capabilities(self, plugin: GatewayPlugin) -> list[str]:
        """Extract capabilities from plugin instance."""
        capabilities = []
        
        # Check for common capabilities
        if hasattr(plugin, 'supports_text') and plugin.supports_text:
            capabilities.append('text')
        if hasattr(plugin, 'supports_media') and plugin.supports_media:
            capabilities.append('media')
        if hasattr(plugin, 'supports_interactive') and plugin.supports_interactive:
            capabilities.append('interactive')
        
        # Default to text if no capabilities specified
        if not capabilities:
            capabilities.append('text')
        
        return capabilities
    
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the gateway with configuration.
        
        Args:
            config: Gateway configuration from workspace.yaml.
        """
        if self._initialized:
            logger.warning("Gateway already initialized")
            return
        
        logger.info("Initializing gateway...")
        
        # Discover plugins
        discovered = self.discover_plugins()
        
        # Load configured plugins
        plugins_config = config.get("plugins", {})
        
        for module_name in discovered:
            plugin_config = plugins_config.get(module_name, {})
            
            if not plugin_config.get("enabled", False):
                logger.info(f"Plugin {module_name} is disabled")
                continue
            
            success = self.load_plugin(module_name, plugin_config.get("config", {}))
            
            if not success:
                logger.warning(f"Failed to load plugin: {module_name}")
        
        self._initialized = True
        logger.info(f"Gateway initialized with {len(self._registry)} plugins")
    
    def get_plugin(self, service_id: str) -> GatewayPlugin | None:
        """Get a plugin instance by service ID.
        
        Args:
            service_id: Service identifier.
            
        Returns:
            Plugin instance or None if not found.
        """
        metadata = self._registry.get(service_id)
        if metadata and metadata.initialized:
            return metadata.instance
        return None
    
    def get_metadata(self, service_id: str) -> PluginMetadata | None:
        """Get plugin metadata by service ID.
        
        Args:
            service_id: Service identifier.
            
        Returns:
            Plugin metadata or None if not found.
        """
        return self._registry.get(service_id)
    
    def list_plugins(self) -> list[PluginMetadata]:
        """List all registered plugins.
        
        Returns:
            List of plugin metadata.
        """
        return list(self._registry.values())
    
    def get_enabled_plugins(self) -> list[PluginMetadata]:
        """List all enabled and initialized plugins.
        
        Returns:
            List of enabled plugin metadata.
        """
        return [m for m in self._registry.values() if m.enabled and m.initialized]
    
    def shutdown(self) -> None:
        """Shutdown the gateway and all plugins."""
        logger.info("Shutting down gateway...")
        
        for metadata in self._registry.values():
            if metadata.instance and hasattr(metadata.instance, 'shutdown'):
                try:
                    metadata.instance.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down plugin {metadata.id}: {e}")
        
        self._registry.clear()
        self._initialized = False
        logger.info("Gateway shutdown complete")
