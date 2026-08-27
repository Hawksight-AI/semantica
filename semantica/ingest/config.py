"""
Configuration Management Module for Ingestion

This module provides centralized configuration management for data ingestion operations,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: INGEST_DEFAULT_SOURCE_TYPE, INGEST_MAX_FILE_SIZE, INGEST_RATE_LIMIT_DELAY, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting ingestion configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for ingestion parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - IngestConfig: Main configuration manager class for ingest module

Example Usage:
    >>> from semantica.ingest.config import ingest_config
    >>> source_type = ingest_config.get("default_source_type", default="file")
    >>> ingest_config.set("default_source_type", "web")
    >>> method_config = ingest_config.get_method_config("file")
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class IngestConfig:
    """Configuration manager for ingest module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self.logger = get_logger("ingest_config")
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
                        self._configs.update(data.get("ingest", {}))
                        self._method_configs.update(data.get("ingest_methods", {}))
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        data = json.load(f) or {}
                        self._configs.update(data.get("ingest", {}))
                        self._method_configs.update(data.get("ingest_methods", {}))
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        data = toml.load(f) or {}
                        if "ingest" in data:
                            self._configs.update(data["ingest"])
                        if "ingest_methods" in data:
                            self._method_configs.update(data["ingest_methods"])
                self.logger.info(f"Loaded ingest config from {config_file}")
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # Ingestion-specific environment variables with INGEST_ prefix
        env_mappings = {
            "INGEST_DEFAULT_SOURCE_TYPE": ("default_source_type", str),
            "INGEST_MAX_FILE_SIZE": ("max_file_size", int),
            "INGEST_RECURSIVE": ("recursive", bool),
            "INGEST_READ_CONTENT": ("read_content", bool),
            "INGEST_RATE_LIMIT_DELAY": ("rate_limit_delay", float),
            "INGEST_RESPECT_ROBOTS": ("respect_robots", bool),
            "INGEST_BATCH_SIZE": ("batch_size", int),
            "INGEST_TIMEOUT": ("timeout", float),
            # MCP server configuration (URL-based, Python/FastMCP only)
            # Note: MCP servers are connected via URL (http://, https://, mcp://)
            # Command/args are not supported in public API
            "MCP_SERVER_URL": ("mcp_server_url", str),
            "MCP_SERVER_TIMEOUT": ("mcp_server_timeout", float),
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

        # Also check for any INGEST_ prefixed variables
        env_prefix = "INGEST_"
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

        # Also check for MCP_ prefixed variables
        mcp_prefix = "MCP_"
        for key, value in os.environ.items():
            if key.startswith(mcp_prefix) and key not in env_mappings:
                config_key = key[len(mcp_prefix) :].lower()
                # Try to convert to appropriate type
                if value.strip().lower() in ("true", "false"):
                    self._configs[f"mcp_{config_key}"] = value.strip().lower() == "true"
                elif value.isdigit():
                    self._configs[f"mcp_{config_key}"] = int(value)
                else:
                    try:
                        self._configs[f"mcp_{config_key}"] = float(value)
                    except ValueError:
                        self._configs[f"mcp_{config_key}"] = value

    def set(self, key: str, value: Any):
        """Set configuration value programmatically."""
        self._configs[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with fallback chain: config -> env -> default."""
        # Check config first
        if key in self._configs:
            return self._configs[key]

        # Check environment variables
        env_key = f"INGEST_{key.upper()}"
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
ingest_config = IngestConfig()
