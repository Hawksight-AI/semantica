"""
Configuration Management Module for Triplet Store

This module provides centralized configuration management for triplet store operations,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: TRIPLET_STORE_DEFAULT_STORE, TRIPLET_STORE_BATCH_SIZE, TRIPLET_STORE_ENABLE_CACHING, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting triplet store configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for triplet store parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - TripletStoreConfig: Main configuration manager class for triplet store module

Example Usage:
    >>> from semantica.triplet_store.config import triplet_store_config
    >>> default_store = triplet_store_config.get("default_store", default="main")
    >>> triplet_store_config.set("default_store", "main")
    >>> method_config = triplet_store_config.get_method_config("add_triplet")
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class TripletStoreConfig:
    """Configuration manager for triplet store module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            config_file: Optional path to configuration file (YAML, JSON, or TOML)
        """
        self.logger = get_logger("triplet_store_config")
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self._method_configs: Dict[str, Dict[str, Any]] = {}

        # Load configuration
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file, environment variables, and defaults."""
        # Load from config file if provided
        if self.config_file:
            self._load_from_file(self.config_file)

        # Load from environment variables
        self._load_from_env()

        # Set defaults
        self._set_defaults()

    def _load_from_file(self, file_path: str) -> None:
        """Load configuration from file."""
        file_path = Path(file_path)
        if not file_path.exists():
            self.logger.warning(f"Config file not found: {file_path}")
            return

        try:
            if file_path.suffix in [".yaml", ".yml"]:
                import yaml

                with open(file_path, "r") as f:
                    config_data = yaml.safe_load(f)
                    if config_data and "triplet_store" in config_data:
                        self._config.update(config_data["triplet_store"])
            elif file_path.suffix == ".json":
                import json

                with open(file_path, "r") as f:
                    config_data = json.load(f)
                    if config_data and "triplet_store" in config_data:
                        self._config.update(config_data["triplet_store"])
            elif file_path.suffix == ".toml":
                import tomli

                with open(file_path, "rb") as f:
                    config_data = tomli.load(f)
                    if config_data and "triplet_store" in config_data:
                        self._config.update(config_data["triplet_store"])
        except Exception as e:
            self.logger.error(f"Failed to load config file: {e}")

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            "TRIPLET_STORE_DEFAULT_STORE": "default_store",
            "TRIPLET_STORE_DEFAULT_GRAPH": "default_graph",
            "TRIPLET_STORE_DEFAULT_GRAPH_URI": "default_graph_uri",
            "TRIPLET_STORE_DEFAULT_NAMED_GRAPHS": "default_graphs",
            "TRIPLET_STORE_BATCH_SIZE": "batch_size",
            "TRIPLET_STORE_ENABLE_CACHING": "enable_caching",
            "TRIPLET_STORE_CACHE_SIZE": "cache_size",
            "TRIPLET_STORE_ENABLE_OPTIMIZATION": "enable_optimization",
            "TRIPLET_STORE_ENABLE_NAMED_GRAPHS": "enable_named_graphs",
            "TRIPLET_STORE_MAX_RETRIES": "max_retries",
            "TRIPLET_STORE_RETRY_DELAY": "retry_delay",
            "TRIPLET_STORE_TIMEOUT": "timeout",
            "TRIPLET_STORE_BLAZEGRAPH_ENDPOINT": "blazegraph_endpoint",
            "TRIPLET_STORE_JENA_ENDPOINT": "jena_endpoint",
            "TRIPLET_STORE_RDF4J_ENDPOINT": "rdf4j_endpoint",
            "TRIPLET_STORE_ANZO_ENDPOINT": "anzo_endpoint",
        }

        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert string values to appropriate types
                if config_key in ["batch_size", "cache_size", "max_retries", "timeout"]:
                    try:
                        self._config[config_key] = int(value)
                    except ValueError:
                        self.logger.warning(
                            f"Invalid integer value for {env_var}: {value}"
                        )
                elif config_key in ["enable_caching", "enable_optimization"]:
                    self._config[config_key] = value.lower() in [
                        "true",
                        "1",
                        "yes",
                        "on",
                    ]
                elif config_key == "enable_named_graphs":
                    self._config[config_key] = value.lower() in [
                        "true",
                        "1",
                        "yes",
                        "on",
                    ]
                elif config_key == "default_graphs":
                    self._config[config_key] = [
                        graph_uri.strip()
                        for graph_uri in value.split(",")
                        if graph_uri.strip()
                    ]
                elif config_key == "retry_delay":
                    try:
                        self._config[config_key] = float(value)
                    except ValueError:
                        self.logger.warning(
                            f"Invalid float value for {env_var}: {value}"
                        )
                else:
                    self._config[config_key] = value

    def _set_defaults(self) -> None:
        """Set default configuration values."""
        defaults = {
            "default_store": None,
            "default_graph": None,
            "default_graph_uri": None,
            "default_graphs": [],
            "batch_size": 1000,
            "enable_caching": True,
            "cache_size": 1000,
            "enable_optimization": True,
            "enable_named_graphs": True,
            "max_retries": 3,
            "retry_delay": 1.0,
            "timeout": 30,
        }

        for key, default_value in defaults.items():
            if key not in self._config:
                self._config[key] = default_value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key
            value: Configuration value
        """
        self._config[key] = value

    def update(self, config: Dict[str, Any]) -> None:
        """
        Update configuration with dictionary.

        Args:
            config: Configuration dictionary
        """
        self._config.update(config)

    def get_method_config(self, method_name: str) -> Dict[str, Any]:
        """
        Get method-specific configuration.

        Args:
            method_name: Method name

        Returns:
            Method configuration dictionary
        """
        return self._method_configs.get(method_name, {}).copy()

    def set_method_config(self, method_name: str, config: Dict[str, Any]) -> None:
        """
        Set method-specific configuration.

        Args:
            method_name: Method name
            config: Method configuration dictionary
        """
        self._method_configs[method_name] = config.copy()

    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration.

        Returns:
            Complete configuration dictionary
        """
        return self._config.copy()

    def reset(self) -> None:
        """Reset configuration to defaults."""
        self._config.clear()
        self._method_configs.clear()
        self._set_defaults()


# Global configuration instance
triplet_store_config = TripletStoreConfig()
