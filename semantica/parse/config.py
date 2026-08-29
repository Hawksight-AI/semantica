"""
Configuration Management Module for Parse

This module provides centralized configuration management for data parsing operations,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: PARSE_DEFAULT_ENCODING, PARSE_OCR_LANGUAGE, PARSE_EXTRACT_TABLES, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting parsing configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for parsing parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - ParseConfig: Main configuration manager class for parse module

Example Usage:
    >>> from semantica.parse.config import parse_config
    >>> encoding = parse_config.get("default_encoding", default="utf-8")
    >>> parse_config.set("default_encoding", "utf-8")
    >>> method_config = parse_config.get_method_config("document")
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class ParseConfig:
    """Configuration manager for parse module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        self.logger = get_logger("parse_config")
        self._configs: Dict[str, Any] = {}
        self._method_configs: Dict[str, Dict] = {}
        self._load_config_file(config_file)
        self._load_env_vars()

    def _load_config_file(self, config_file: Optional[str]):
        if config_file and Path(config_file).exists():
            try:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    import yaml

                    with open(config_file, "r") as f:
                        data = yaml.safe_load(f) or {}
                        self._configs.update(data.get("parse", {}))
                        self._method_configs.update(data.get("parse_methods", {}))
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        data = json.load(f) or {}
                        self._configs.update(data.get("parse", {}))
                        self._method_configs.update(data.get("parse_methods", {}))
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        data = toml.load(f) or {}
                        if "parse" in data:
                            self._configs.update(data["parse"])
                        if "parse_methods" in data:
                            self._method_configs.update(data["parse_methods"])
                self.logger.info(f"Loaded parse config from {config_file}")
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        env_mappings = {
            "PARSE_DEFAULT_ENCODING": ("default_encoding", str),
            "PARSE_OCR_LANGUAGE": ("ocr_language", str),
            "PARSE_EXTRACT_TABLES": ("extract_tables", bool),
            "PARSE_EXTRACT_IMAGES": ("extract_images", bool),
            "PARSE_EXTRACT_METADATA": ("extract_metadata", bool),
            "PARSE_JS_RENDERING": ("js_rendering", bool),
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

        env_prefix = "PARSE_"
        for key, value in os.environ.items():
            if key.startswith(env_prefix) and key not in env_mappings:
                config_key = key[len(env_prefix) :].lower()
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
        if key in self._configs:
            return self._configs[key]

        env_key = f"PARSE_{key.upper()}"
        value = os.getenv(env_key)
        if value:
            try:
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
parse_config = ParseConfig()
