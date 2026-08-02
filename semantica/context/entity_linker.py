"""
Entity Linker for Context Engineering

This module provides comprehensive entity linking capabilities for context
engineering, linking entities across different sources to build the web of
context. It assigns each entity a unique URL/URI and connects them meaningfully
to enable semantic understanding.

Algorithms Used:

URI Generation:
    - Hash-based URI: MD5 hash-based URI generation for entities without text
    - Text-based URI: URL-safe text encoding for entity text
    - Type-based URI: Entity type inclusion in URI
    - URI Registry: Dictionary-based URI-to-entity mapping

Entity Linking:
    - Text Similarity: Word overlap-based similarity calculation (Jaccard-like)
    - Knowledge Graph Lookup: Entity matching in knowledge graph
    - Similarity Threshold: Threshold-based entity matching
    - Cross-Document Linking: Entity linking across multiple documents
    - Bidirectional Linking: Symmetric relationship creation

Entity Web Construction:
    - Graph Building: Graph construction from entity links
    - Link Aggregation: Link counting and statistics
    - Entity Registry: Entity-to-URI mapping
    - Link Storage: Dictionary-based link storage (entity_id -> List[EntityLink])

Key Features:
    - Links entities across different sources
    - Assigns unique identifiers (URLs/URIs) to entities
    - Creates semantic connections between entities
    - Builds entity connection web
    - Supports cross-document entity linking
    - Enables entity disambiguation and resolution
    - Similarity-based entity matching
    - Bidirectional entity linking
    - Entity web construction and statistics
    - Configurable similarity thresholds

Main Classes:
    - EntityLink: Entity link data structure with source_entity_id, target_entity_id,
      link_type, confidence, source, metadata
    - LinkedEntity: Linked entity with context including entity_id, uri, text, type,
      linked_entities, context, confidence
    - EntityLinker: Entity linker for context engineering

Example Usage:
    >>> from semantica.context import EntityLinker
    >>> linker = EntityLinker(knowledge_graph=kg)
    >>> uri = linker.assign_uri("entity_1", "Python", "PROGRAMMING_LANGUAGE")
    >>> linked_entities = linker.link(
    ...     "Python is a programming language", entities=entities
    ... )
    >>> linker.link_entities("entity_1", "entity_2", "related_to", confidence=0.9)
    >>> web = linker.build_entity_web()

Author: Semantica Contributors
License: MIT
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ..utils.types import EntityDict


@dataclass
class EntityLink:
    """Entity link definition."""

    source_entity_id: str
    target_entity_id: str
    link_type: str  # "same_as", "related_to", "part_of", etc.
    confidence: float = 1.0
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkedEntity:
    """Linked entity with context."""

    entity_id: str
    uri: str
    text: str
    type: str
    linked_entities: List[EntityLink] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


class EntityLinker:
    """
    Entity linker for context engineering.

    • Links entities across different sources
    • Assigns unique identifiers (URLs/URIs) to entities
    • Creates semantic connections between entities
    • Builds entity connection web
    • Supports cross-document entity linking
    • Enables entity disambiguation and resolution
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize entity linker.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - knowledge_graph: Knowledge graph for entity lookup
                - similarity_threshold: Similarity threshold for linking (default: 0.8)
                - base_uri: Base URI for entity URIs
                - enable_cross_document_linking: Enable cross-document linking
                  (default: True)
        """
        self.logger = get_logger("entity_linker")
        self.config = config or {}
        self.config.update(kwargs)

        self.knowledge_graph = self.config.get("knowledge_graph")
        self.similarity_threshold = self.config.get("similarity_threshold", 0.8)
        self.base_uri = self.config.get("base_uri", "https://semantica.dev/entity/")
        self.enable_cross_document_linking = self.config.get(
            "enable_cross_document_linking", True
        )

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Entity registry: entity_id -> URI
        self.entity_registry: Dict[str, str] = {}

        # Entity links: entity_id -> List[EntityLink]
        self.entity_links: Dict[str, List[EntityLink]] = {}

    def assign_uri(
        self,
        entity_id: str,
        entity_text: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> str:
        """
        Assign unique URI to entity.

        Args:
            entity_id: Entity identifier
            entity_text: Entity text/name
            entity_type: Entity type

        Returns:
            Entity URI
        """
        if entity_id in self.entity_registry:
            return self.entity_registry[entity_id]

        # Generate URI from entity information
        if entity_text:
            # Create URI-safe identifier
            uri_safe = quote(entity_text.lower().replace(" ", "_"), safe="")
            uri = f"{self.base_uri}{uri_safe}"
        else:
            # Use hash of entity_id
            entity_hash = hashlib.md5(entity_id.encode()).hexdigest()[:8]  # nosec B324 - deterministic URI suffix, not security-sensitive
            uri = f"{self.base_uri}{entity_hash}"

        # Add type if available
        if entity_type:
            uri = f"{uri}#{entity_type.lower()}"

        self.entity_registry[entity_id] = uri
        self.logger.debug(f"Assigned URI {uri} to entity {entity_id}")

        return uri

    def link(
        self,
        text: str,
        entities: Optional[List[EntityDict]] = None,
        context: Optional[List[Dict[str, Any]]] = None,
    ) -> List[LinkedEntity]:
        """
        Link entities in text to knowledge graph.

        Args:
            text: Input text
            entities: List of entities to link
            context: Additional context information

        Returns:
            List of linked entities
        """
        # Track entity linking
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="context",
            submodule="EntityLinker",
            message="Linking entities in text",
        )

        try:
            if not entities:
                entities = []

            linked_entities = []

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Linking {len(entities)} entities..."
            )

            for entity in entities:
                entity_id = entity.get("id") or entity.get("entity_id")
                entity_text = (
                    entity.get("text") or entity.get("label") or entity.get("name", "")
                )
                entity_type = entity.get("type") or entity.get("entity_type", "UNKNOWN")

                if not entity_id:
                    # Generate entity_id if not present
                    entity_id = self._generate_entity_id(entity_text, entity_type)

                # Assign URI
                uri = self.assign_uri(entity_id, entity_text, entity_type)

                # Find linked entities
                linked_entity_links = self._find_linked_entities(
                    entity_id, entity_text, entity_type, entities, context
                )

                linked_entity = LinkedEntity(
                    entity_id=entity_id,
                    uri=uri,
                    text=entity_text,
                    type=entity_type,
                    linked_entities=linked_entity_links,
                    context=entity.get("metadata", {}),
                    confidence=entity.get("confidence", 1.0),
                )

                linked_entities.append(linked_entity)

                # Store links
                if entity_id not in self.entity_links:
                    self.entity_links[entity_id] = []
                self.entity_links[entity_id].extend(linked_entity_links)

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

        return linked_entities

    def link_entities(
        self,
        entity1_id: str,
        entity2_id: str,
        link_type: str = "related_to",
        confidence: float = 1.0,
        source: Optional[str] = None,
        **metadata,
    ) -> bool:
        """
        Create explicit link between two entities.

        Args:
            entity1_id: First entity ID
            entity2_id: Second entity ID
            link_type: Link type
            confidence: Link confidence
            source: Source of the link
            **metadata: Additional metadata

        Returns:
            True if link created successfully
        """
        # Track entity linking
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="context",
            submodule="EntityLinker",
            message=f"Linking {entity1_id} -> {entity2_id}",
        )

        try:
            link = EntityLink(
                source_entity_id=entity1_id,
                target_entity_id=entity2_id,
                link_type=link_type,
                confidence=confidence,
                source=source,
                metadata=metadata,
            )

            if entity1_id not in self.entity_links:
                self.entity_links[entity1_id] = []

            self.entity_links[entity1_id].append(link)

            # Create bidirectional link if appropriate
            if link_type in ["related_to", "same_as"]:
                reverse_link = EntityLink(
                    source_entity_id=entity2_id,
                    target_entity_id=entity1_id,
                    link_type=link_type,
                    confidence=confidence,
                    source=source,
                    metadata=metadata,
                )

                if entity2_id not in self.entity_links:
                    self.entity_links[entity2_id] = []
                self.entity_links[entity2_id].append(reverse_link)

            self.logger.debug(f"Linked {entity1_id} --{link_type}--> {entity2_id}")

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Linked {entity1_id} -> {entity2_id}",
            )
            return True

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def get_entity_links(self, entity_id: str) -> List[EntityLink]:
        """
        Get all links for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List of entity links
        """
        return self.entity_links.get(entity_id, [])

    def get_entity_uri(self, entity_id: str) -> Optional[str]:
        """
        Get URI for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity URI or None if not found
        """
        return self.entity_registry.get(entity_id)

    def find_similar_entities(
        self,
        entity_text: str,
        entity_type: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find similar entities in knowledge graph.

        Args:
            entity_text: Entity text to search for
            entity_type: Optional entity type filter
            threshold: Similarity threshold (uses default if None)

        Returns:
            List of dicts with entity_id, text, type, uri, and similarity
        """
        threshold = threshold or self.similarity_threshold

        if not self.knowledge_graph:
            return []

        # Simple text-based similarity (can be enhanced with embeddings)
        similar_entities = []

        entities = self.knowledge_graph.get("entities", [])

        for entity in entities:
            if entity_type and entity.get("type") != entity_type:
                continue

            entity_text2 = (
                entity.get("text") or entity.get("label") or entity.get("name", "")
            )

            # Calculate simple similarity (can be enhanced)
            similarity = self._calculate_text_similarity(
                entity_text.lower(), entity_text2.lower()
            )

            if similarity >= threshold:
                entity_id = entity.get("id") or entity.get("entity_id")
                if entity_id:
                    similar_entities.append({
                        "entity_id": entity_id,
                        "text": entity_text2,
                        "type": entity.get("type", ""),
                        "uri": self.entity_registry.get(entity_id, ""),
                        "similarity": similarity,
                    })

        # Sort by similarity
        similar_entities.sort(key=lambda x: x["similarity"], reverse=True)

        return similar_entities

    def _find_linked_entities(
        self,
        entity_id: str,
        entity_text: str,
        entity_type: str,
        all_entities: List[EntityDict],
        context: Optional[List[Dict[str, Any]]],
    ) -> List[EntityLink]:
        """Find entities linked to this entity."""
        links = []

        # Find similar entities in knowledge graph
        if self.knowledge_graph:
            similar = self.find_similar_entities(entity_text, entity_type)
            for similar_entity in similar:
                similar_id = similar_entity.get("entity_id")
                similarity = similar_entity.get("similarity", 0.0)
                if not similar_id:
                    continue
                if similar_id != entity_id:
                    links.append(
                        EntityLink(
                            source_entity_id=entity_id,
                            target_entity_id=similar_id,
                            link_type="same_as" if similarity >= 0.9 else "related_to",
                            confidence=similarity,
                            metadata={"similarity": similarity},
                        )
                    )

        # Find relationships in context
        if context:
            for ctx in context:
                relationships = ctx.get("relationships", [])
                for rel in relationships:
                    source_id = rel.get("source_id")
                    target_id = rel.get("target_id")

                    if source_id == entity_id:
                        links.append(
                            EntityLink(
                                source_entity_id=entity_id,
                                target_entity_id=target_id,
                                link_type=rel.get("type", "related_to"),
                                confidence=rel.get("confidence", 1.0),
                                source=ctx.get("source"),
                            )
                        )
                    elif target_id == entity_id:
                        links.append(
                            EntityLink(
                                source_entity_id=entity_id,
                                target_entity_id=source_id,
                                link_type=rel.get("type", "related_to"),
                                confidence=rel.get("confidence", 1.0),
                                source=ctx.get("source"),
                            )
                        )

        return links

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity."""
        if not text1 or not text2:
            return 0.0

        # Simple word overlap similarity
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def _generate_entity_id(self, text: str, entity_type: str) -> str:
        """Generate entity ID from text and type."""
        entity_hash = hashlib.md5(f"{text}_{entity_type}".encode()).hexdigest()[:12]  # nosec B324 - deterministic entity ID, not security-sensitive
        return f"{entity_type.lower()}_{entity_hash}"

    def build_entity_web(self) -> Dict[str, Any]:
        """
        Build entity connection web.

        Returns:
            Entity web dictionary
        """
        web = {
            "entities": {},
            "links": [],
            "statistics": {
                "total_entities": len(self.entity_registry),
                "total_links": sum(len(links) for links in self.entity_links.values()),
            },
        }

        # Add entities
        for entity_id, uri in self.entity_registry.items():
            web["entities"][entity_id] = {
                "uri": uri,
                "links": len(self.entity_links.get(entity_id, [])),
            }

        # Add links
        for entity_id, links in self.entity_links.items():
            for link in links:
                web["links"].append(
                    {
                        "source": link.source_entity_id,
                        "target": link.target_entity_id,
                        "type": link.link_type,
                        "confidence": link.confidence,
                    }
                )

        return web

    # Linking Methods
    def link_text(
        self, text: str, entities: Optional[List[EntityDict]] = None
    ) -> List[LinkedEntity]:
        """
        Link entities in text.

        Args:
            text: Text containing entities
            entities: List of entities to link (optional)

        Returns:
            List of LinkedEntity objects

        Example:
            >>> linked = linker.link_text("Python is used for ML", entities=[...])
        """
        return self.link(text, entities=entities or [])

    def link_batch(self, entities: List[EntityDict]) -> List[LinkedEntity]:
        """
        Link multiple entities.

        Args:
            entities: List of entities to link

        Returns:
            List of LinkedEntity objects

        Example:
            >>> linked = linker.link_batch(entities)
        """
        linked_results = []
        for entity in entities:
            uri = self.assign_uri(
                entity.get("id", ""),
                entity.get("text"),
                entity.get("type"),
            )

            # Find similar entities
            similar = self.find_similar_entities(
                entity.get("text", ""),
                entity.get("type", ""),
                threshold=self.similarity_threshold,
            )

            linked_entities = []
            for similar_entity in similar:
                similar_id = similar_entity.get("entity_id")
                similarity = similar_entity.get("similarity", 0.0)
                if not similar_id:
                    continue
                linked_entities.append(
                    EntityLink(
                        source_entity_id=entity.get("id", ""),
                        target_entity_id=similar_id,
                        link_type="similar_to",
                        confidence=similarity,
                    )
                )

            linked_results.append(
                LinkedEntity(
                    entity_id=entity.get("id", ""),
                    uri=uri,
                    text=entity.get("text", ""),
                    type=entity.get("type", ""),
                    linked_entities=linked_entities,
                    confidence=1.0,
                )
            )

        return linked_results

    # Search Methods
    def find_similar(
        self, entity: Union[str, EntityDict], threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Find similar entities.

        Args:
            entity: Entity text or EntityDict
            threshold: Similarity threshold (default: 0.8)

        Returns:
            List of dicts with entity_id, text, type, uri, and similarity

        Example:
            >>> similar = linker.find_similar("Python", threshold=0.8)
        """
        if isinstance(entity, dict):
            text = entity.get("text", "")
            entity_type = entity.get("type", "")
        else:
            text = entity
            entity_type = ""

        return self.find_similar_entities(text, entity_type, threshold=threshold)

    def find_by_text(self, text: str, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """
        Find by text.

        Args:
            text: Text to search for
            threshold: Similarity threshold (default: 0.8)

        Returns:
            List of matching entity dicts

        Example:
            >>> entities = linker.find_by_text("Python", threshold=0.8)
        """
        results = []
        for entity_id, uri in self.entity_registry.items():
            # Get entity text from knowledge graph or registry
            if self.knowledge_graph:
                nodes = self.knowledge_graph.get("nodes", [])
                for node in nodes:
                    if node.get("id") == entity_id:
                        node_content = node.get("content", "")
                        similarity = self._calculate_similarity(text, node_content)
                        if similarity >= threshold:
                            results.append(
                                {
                                    "entity_id": entity_id,
                                    "uri": uri,
                                    "text": node_content,
                                    "type": node.get("type", ""),
                                    "similarity": similarity,
                                }
                            )
                        break
        return sorted(results, key=lambda x: x.get("similarity", 0), reverse=True)

    def find_by_type(self, type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find by type.

        Args:
            type: Entity type
            limit: Maximum results (default: 10)

        Returns:
            List of entity dicts of specified type

        Example:
            >>> entities = linker.find_by_type("PROGRAMMING_LANGUAGE", limit=10)
        """
        results = []
        if self.knowledge_graph:
            nodes = self.knowledge_graph.get("nodes", [])
            for node in nodes:
                if node.get("type") == type:
                    entity_id = node.get("id", "")
                    uri = self.entity_registry.get(entity_id, "")
                    results.append(
                        {
                            "entity_id": entity_id,
                            "uri": uri,
                            "text": node.get("content", ""),
                            "type": type,
                        }
                    )
                    if len(results) >= limit:
                        break
        return results

    def find_related(self, entity_id: str, max_hops: int = 2) -> List[Dict[str, Any]]:
        """
        Find related entities.

        Args:
            entity_id: Entity ID
            max_hops: Maximum hops (default: 2)

        Returns:
            List of related entity dicts

        Example:
            >>> related = linker.find_related("entity_123", max_hops=2)
        """
        related = []
        visited = {entity_id}
        current_level = {entity_id}

        for hop in range(max_hops):
            next_level = set()
            for current_id in current_level:
                links = self.entity_links.get(current_id, [])
                for link in links:
                    target_id = link.target_entity_id
                    if target_id not in visited:
                        visited.add(target_id)
                        next_level.add(target_id)

                        # Get entity info
                        uri = self.entity_registry.get(target_id, "")
                        if self.knowledge_graph:
                            nodes = self.knowledge_graph.get("nodes", [])
                            for node in nodes:
                                if node.get("id") == target_id:
                                    related.append(
                                        {
                                            "entity_id": target_id,
                                            "uri": uri,
                                            "text": node.get("content", ""),
                                            "type": node.get("type", ""),
                                            "link_type": link.link_type,
                                            "confidence": link.confidence,
                                            "hop": hop + 1,
                                        }
                                    )
                                    break

            current_level = next_level

        return related

    # URI Methods
    def get_uri(self, entity_id: str) -> Optional[str]:
        """
        Get URI for entity.

        Args:
            entity_id: Entity ID

        Returns:
            URI or None if not found

        Example:
            >>> uri = linker.get_uri("entity_123")
        """
        return self.entity_registry.get(entity_id)

    def get_all_uris(self) -> Dict[str, str]:
        """
        Get all URIs.

        Returns:
            Dict mapping entity_id to URI

        Example:
            >>> uris = linker.get_all_uris()
        """
        return self.entity_registry.copy()

    def resolve_uri(self, uri: str) -> Optional[Dict[str, Any]]:
        """
        Resolve URI to entity.

        Args:
            uri: URI to resolve

        Returns:
            Entity dict or None if not found

        Example:
            >>> entity = linker.resolve_uri("https://semantica.dev/entity/python")
        """
        # Find entity_id by URI
        for entity_id, entity_uri in self.entity_registry.items():
            if entity_uri == uri:
                # Get entity info
                if self.knowledge_graph:
                    nodes = self.knowledge_graph.get("nodes", [])
                    for node in nodes:
                        if node.get("id") == entity_id:
                            return {
                                "entity_id": entity_id,
                                "uri": uri,
                                "text": node.get("content", ""),
                                "type": node.get("type", ""),
                            }
                return {
                    "entity_id": entity_id,
                    "uri": uri,
                }
        return None

    # Statistics
    def link_count(self, entity_id: str) -> int:
        """
        Get link count for entity.

        Args:
            entity_id: Entity ID

        Returns:
            Number of links for entity

        Example:
            >>> count = linker.link_count("entity_123")
        """
        return len(self.entity_links.get(entity_id, []))

    def stats(self) -> Dict[str, Any]:
        """
        Get statistics.

        Returns:
            Statistics dict

        Example:
            >>> stats = linker.stats()
        """
        web = self.build_entity_web()
        return {
            "total_entities": web["statistics"]["total_entities"],
            "total_links": web["statistics"]["total_links"],
            "average_links_per_entity": (
                web["statistics"]["total_links"] / web["statistics"]["total_entities"]
                if web["statistics"]["total_entities"] > 0 else 0
            ),
        }

    def most_linked(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most linked entities.

        Args:
            limit: Maximum results (default: 10)

        Returns:
            List of entity dicts sorted by link count

        Example:
            >>> top = linker.most_linked(limit=10)
        """
        entity_link_counts = []
        for entity_id, links in self.entity_links.items():
            uri = self.entity_registry.get(entity_id, "")
            entity_link_counts.append(
                {
                    "entity_id": entity_id,
                    "uri": uri,
                    "link_count": len(links),
                }
            )

        # Sort by link count
        entity_link_counts.sort(key=lambda x: x["link_count"], reverse=True)

        # Add entity text if available
        if self.knowledge_graph:
            nodes = self.knowledge_graph.get("nodes", [])
            node_map = {node.get("id"): node for node in nodes}
            for item in entity_link_counts:
                node = node_map.get(item["entity_id"])
                if node:
                    item["text"] = node.get("content", "")
                    item["type"] = node.get("type", "")

        return entity_link_counts[:limit]
