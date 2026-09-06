"""
Configuration Management Module for Export

This module provides centralized configuration management for export operations,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: EXPORT_DEFAULT_FORMAT, EXPORT_OUTPUT_DIR, EXPORT_INCLUDE_METADATA, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting export configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for export parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - ExportConfig: Main configuration manager class for export module

Example Usage:
    >>> from semantica.export.config import export_config
    >>> format = export_config.get("default_format", default="json")
    >>> export_config.set("default_format", "json-ld")
    >>> method_config = export_config.get_method_config("rdf")
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class ExportConfig:
    """Configuration manager for export module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self.logger = get_logger("export_config")
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
                        self._configs.update(data.get("export", {}))
                        self._method_configs.update(data.get("export_methods", {}))
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        data = json.load(f) or {}
                        self._configs.update(data.get("export", {}))
                        self._method_configs.update(data.get("export_methods", {}))
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        data = toml.load(f) or {}
                        if "export" in data:
                            self._configs.update(data["export"])
                        if "export_methods" in data:
                            self._method_configs.update(data["export_methods"])
                self.logger.info(f"Loaded export config from {config_file}")
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # Export-specific environment variables with EXPORT_ prefix
        env_mappings = {
            "EXPORT_DEFAULT_FORMAT": ("default_format", str),
            "EXPORT_OUTPUT_DIR": ("output_dir", str),
            "EXPORT_INCLUDE_METADATA": ("include_metadata", bool),
            "EXPORT_INDENT": ("indent", int),
            "EXPORT_ENCODING": ("encoding", str),
            "EXPORT_DELIMITER": ("delimiter", str),
            "EXPORT_NAMESPACE_BASE": ("namespace_base", str),
            "EXPORT_VALIDATE": ("validate", bool),
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

        # Also check for any EXPORT_ prefixed variables
        env_prefix = "EXPORT_"
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
        env_key = f"EXPORT_{key.upper()}"
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
export_config = ExportConfig()
