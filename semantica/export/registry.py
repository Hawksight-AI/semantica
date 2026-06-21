"""
Method Registry Module for Export

This module provides a method registry system for registering custom export methods,
enabling extensibility and community contributions to the export toolkit.

Supported Registration Types:
    - Method Registry: Register custom export methods for:
        * "rdf": RDF export methods
        * "json": JSON/JSON-LD export methods
        * "csv": CSV export methods
        * "neo4j_csv": Neo4j Bulk CSV export methods
        * "graph": Graph format export methods
        * "yaml": YAML export methods
        * "owl": OWL export methods
        * "vector": Vector export methods
        * "lpg": LPG (Labeled Property Graph) export methods
        * "report": Report generation methods
        * "export": General export methods

Algorithms Used:
    - Registry Pattern: Dictionary-based registration and lookup
    - Dynamic Registration: Runtime function registration
    - Type Checking: Type validation for registered components
    - Lookup Algorithms: Hash-based O(1) lookup for methods
    - Task-based Organization: Hierarchical organization by task type

Key Features:
    - Method registry for custom export methods
    - Task-based method organization (rdf, json, csv, neo4j_csv, graph,
      yaml, owl, vector, lpg, report, export)
    - Dynamic registration and unregistration
    - Easy discovery of available methods
    - Support for community-contributed extensions

Main Classes:
    - MethodRegistry: Registry for custom export methods

Global Instances:
    - method_registry: Global method registry instance

Example Usage:
    >>> from semantica.export.registry import method_registry
    >>> method_registry.register("json", "custom_method", custom_json_export_function)
    >>> available = method_registry.list_all("json")
"""

from typing import Callable, Dict, List, Optional


class MethodRegistry:
    """Registry for custom export methods."""

    _methods: Dict[str, Dict[str, Callable]] = {
        "rdf": {},
        "json": {},
        "csv": {},
        "neo4j_csv": {},
        "graph": {},
        "yaml": {},
        "owl": {},
        "vector": {},
        "lpg": {},
        "report": {},
        "export": {},
    }

    @classmethod
    def register(cls, task: str, name: str, method_func: Callable):
        """
        Register a custom export method.

        Args:
            task: Task type ("rdf", "json", "csv", "neo4j_csv", "graph",
                "yaml", "owl", "vector", "lpg", "report", "export")
            name: Method name
            method_func: Method function
        """
        if task not in cls._methods:
            cls._methods[task] = {}
        cls._methods[task][name] = method_func

    @classmethod
    def get(cls, task: str, name: str) -> Optional[Callable]:
        """
        Get method by task and name.

        Args:
            task: Task type ("rdf", "json", "csv", "neo4j_csv", "graph",
                "yaml", "owl", "vector", "lpg", "report", "export")
            name: Method name

        Returns:
            Method function or None
        """
        return cls._methods.get(task, {}).get(name)

    @classmethod
    def list_all(cls, task: Optional[str] = None) -> Dict[str, List[str]]:
        """
        List all registered methods.

        Args:
            task: Optional task type to filter by

        Returns:
            Dictionary mapping task types to method names
        """
        if task:
            return {task: list(cls._methods.get(task, {}).keys())}
        return {t: list(m.keys()) for t, m in cls._methods.items()}

    @classmethod
    def unregister(cls, task: str, name: str):
        """
        Unregister a method.

        Args:
            task: Task type ("rdf", "json", "csv", "neo4j_csv", "graph",
                "yaml", "owl", "vector", "lpg", "report", "export")
            name: Method name
        """
        if task in cls._methods and name in cls._methods[task]:
            del cls._methods[task][name]

    @classmethod
    def clear(cls, task: Optional[str] = None):
        """
        Clear all registered methods for a task or all tasks.

        Args:
            task: Optional task type to clear (clears all if None)
        """
        if task:
            if task in cls._methods:
                cls._methods[task].clear()
        else:
            for task_dict in cls._methods.values():
                task_dict.clear()


# Global registry
method_registry = MethodRegistry()
