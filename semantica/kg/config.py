"""
Configuration Management Module for Knowledge Graph

This module provides centralized configuration management for knowledge graph operations,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: KG_MERGE_ENTITIES, KG_RESOLUTION_STRATEGY, KG_ENABLE_TEMPORAL, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting KG configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for KG parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - KGConfig: Main configuration manager class for KG module

Example Usage:
    >>> from semantica.kg.config import kg_config
    >>> merge_entities = kg_config.get("merge_entities", default=True)
    >>> kg_config.set("merge_entities", False)
    >>> method_config = kg_config.get_method_config("build")
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class KGConfig:
    """Configuration manager for knowledge graph module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self.logger = get_logger("kg_config")
        self._configs: Dict[str, Any] = {}
        self._method_configs: Dict[str, Dict] = {}
        self._load_config_file(config_file)
        self._load_env_vars()

    def _load_config_file(self, config_file: Optional[str]):
        """Load configuration from file."""
        if config_file and Path(config_file).exists():
            try:
                # Support YAML, JSON, TOML
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    import yaml

                    with open(config_file, "r") as f:
                        data = yaml.safe_load(f) or {}
                        self._configs.update(data.get("kg", {}))
                        self._method_configs.update(data.get("kg_methods", {}))
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        data = json.load(f) or {}
                        self._configs.update(data.get("kg", {}))
                        self._method_configs.update(data.get("kg_methods", {}))
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        data = toml.load(f) or {}
                        if "kg" in data:
                            self._configs.update(data["kg"])
                        if "kg_methods" in data:
                            self._method_configs.update(data["kg_methods"])
                self.logger.info(f"Loaded KG config from {config_file}")
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # KG-specific environment variables with KG_ prefix
        env_mappings = {
            "KG_MERGE_ENTITIES": ("merge_entities", bool),
            "KG_RESOLUTION_STRATEGY": ("resolution_strategy", str),
            "KG_RESOLVE_CONFLICTS": ("resolve_conflicts", bool),
            "KG_ENABLE_TEMPORAL": ("enable_temporal", bool),
            "KG_TEMPORAL_GRANULARITY": ("temporal_granularity", str),
            "KG_TRACK_HISTORY": ("track_history", bool),
            "KG_VERSION_SNAPSHOTS": ("version_snapshots", bool),
            "KG_SIMILARITY_THRESHOLD": ("similarity_threshold", float),
            "KG_CONFLICT_STRATEGY": ("conflict_strategy", str),
        }

        for env_key, (config_key, type_func) in env_mappings.items():
            value = os.getenv(env_key)
            if value:
                try:
                    if type_func == bool:
                        self._configs[config_key] = value.strip().lower() in (
                            "true",
                            "1",
                            "yes",
                            "on",
                        )
                    else:
                        self._configs[config_key] = type_func(value)
                except (ValueError, TypeError):
                    self.logger.warning(f"Failed to parse {env_key}={value}")

        # Also check for any KG_ prefixed variables
        env_prefix = "KG_"
        for key, value in os.environ.items():
            if key.startswith(env_prefix) and key not in env_mappings:
                config_key = key[len(env_prefix) :].lower()
                # Try to convert to appropriate type
                if value.strip().lower() in ("true", "false"):
                    self._configs[config_key] = value.strip().lower() == "true"
                elif value.isdigit():
                    self._configs[config_key] = int(value)
                else:
                    try:
                        self._configs[config_key] = float(value)
                    except ValueError:
                        self._configs[config_key] = value

    def set(self, key: str, value: Any):
        """Set configuration value programmatically."""
        self._configs[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with fallback chain: config -> env -> default."""
        # Check config first
        if key in self._configs:
            return self._configs[key]

        # Check environment variables
        env_key = f"KG_{key.upper()}"
        value = os.getenv(env_key)
        if value:
            try:
                # Try to convert to appropriate type
                if isinstance(default, bool):
                    return value.strip().lower() in ("true", "1", "yes", "on")
                elif isinstance(default, int):
                    return int(value)
                elif isinstance(default, float):
                    return float(value)
                return value
            except (ValueError, TypeError):
                pass

        return default

    def set_method_config(self, method: str, **config):
        """Set method-specific configuration."""
        self._method_configs[method] = config

    def get_method_config(self, method: str) -> Dict:
        """Get method-specific configuration."""
        return self._method_configs.get(method, {})

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration."""
        return {
            "config": self._configs.copy(),
            "method_configs": self._method_configs.copy(),
        }


# Global config instance
kg_config = KGConfig()
