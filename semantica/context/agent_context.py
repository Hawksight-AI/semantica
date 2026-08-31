"""
High-Level Agent Context Interface

Simplified interface for agent context management, RAG, and GraphRAG with
auto-detection of content types and retrieval strategies.

Core Features:
    - Generic methods: store(), retrieve(), forget(), conversation()
    - Auto-detection: Memory vs documents, RAG vs GraphRAG
    - Boolean flags: Simple True/False parameters for common options
    - User-friendly: Easy to use interface for agentic systems

Advanced Decision Tracking:
    - Complete decision lifecycle management
    - Hybrid precedent search (semantic + structural + vector)
    - Causal chain analysis and decision influence tracing
    - Policy engine for governance and compliance
    - Explainable AI with decision path tracing

KG Algorithm Integration:
    - Centrality Analysis: Degree, betweenness, closeness, eigenvector
    - Community Detection: Modularity-based community identification
    - Node Embeddings: Node2Vec embeddings for similarity
    - Path Finding: Shortest path and advanced path algorithms
    - Link Prediction: Relationship prediction between entities
    - Similarity Calculation: Multi-type similarity measures

Vector Store Integration:
    - Hybrid Search: Semantic + structural similarity
    - Custom Similarity Weights: Configurable scoring
    - Advanced Precedent Search: KG-enhanced similarity
    - Multi-Embedding Support: Multiple embedding types

Key Methods:
    - store(): Store content with auto-detection
    - retrieve(): Retrieve relevant context with hybrid search
    - record_decision(): Record decisions with full context
    - find_precedents(): Find similar decisions with advanced search
    - find_precedents_advanced(): Enhanced search with KG features
    - analyze_decision_influence(): Analyze influence using KG algorithms
    - predict_decision_relationships(): Predict decision relationships
    - get_context_insights(): Get comprehensive system analytics
    - get_causal_chain(): Trace decision causality
    - trace_decision_explainability(): Explain decision reasoning

Example Usage:
    >>> from semantica.context import AgentContext
    >>> context = AgentContext(vector_store=vs, knowledge_graph=kg, 
    ...                       decision_tracking=True,
    ...                       advanced_analytics=True,
    ...                       kg_algorithms=True,
    ...                       vector_store_features=True,
    ...                       graph_expansion=True)
    >>> memory_id = context.store("User asked about Python", conversation_id="conv1")
    >>> results = context.retrieve("Python programming")
    >>> decision_id = context.record_decision(category="approval", 
    ...                                      scenario="Loan application",
    ...                                      reasoning="Good credit score",
    ...                                      outcome="approved",
    ...                                      confidence=0.95)
    >>> precedents = context.find_precedents_advanced("Loan application", 
    ...                                               category="approval",
    ...                                               use_kg_features=True)
    >>> influence = context.analyze_decision_influence(decision_id)
    >>> insights = context.get_context_insights()

Production Use Cases:
    - Banking: Mortgage approvals, credit decisions, risk assessment
    - Healthcare: Treatment approvals, diagnostic decisions, policy compliance
    - E-commerce: Personalization decisions, recommendation systems
    - Legal: Case precedent analysis, decision consistency
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from ..utils.helpers import classify_path_distance
from ..utils.logging import get_logger
from .agent_memory import AgentMemory
from .context_retriever import ContextRetriever, RetrievedContext
from .entity_linker import EntityLinker
from .decision_models import Decision
from .decision_recorder import DecisionRecorder
from .decision_query import DecisionQuery
from .causal_analyzer import CausalChainAnalyzer
from .policy_engine import PolicyEngine
from ..change_management import TemporalVersionManager


class AgentContext:
    """
    High-level interface for agent context management, RAG, and GraphRAG.

    Provides generic methods (store, retrieve, forget, conversation) that auto-detect
    content types and retrieval strategies. Uses boolean flags for common options.

    Attributes:
        vector_store: Vector store instance
        knowledge_graph: Knowledge graph instance (optional)
        memory: AgentMemory instance (via property)
        retriever: ContextRetriever instance (via property, if knowledge_graph
            available)
        graph_builder: ContextGraph instance (via property, if knowledge_graph
            supports building)

    Main Methods:
        - store(): Store memory or documents (auto-detects type)
        - retrieve(): Retrieve context (auto-detects RAG vs GraphRAG)
        - forget(): Delete memories
        - conversation(): Get conversation history
        - get_memory(): Get specific memory by ID
        - stats(): Get memory statistics
        - link(): Link entities in text
        - build_graph(): Build context graph manually

    Example:
        >>> context = AgentContext(vector_store=vs, knowledge_graph=kg)
        >>> memory_id = context.store("User likes Python", conversation_id="conv1")
        >>> results = context.retrieve("Python programming")
        >>> stats = context.stats()
        >>> memory = context.get_memory(memory_id)
    """

    def __init__(
        self,
        vector_store: Any,
        knowledge_graph: Optional[Any] = None,
        retention_days: Optional[int] = 30,
        max_memories: int = 10000,
        graph_expansion: bool = True,
        max_expansion_hops: int = 2,
        hybrid_alpha: float = 0.5,
        decision_tracking: bool = False,
        advanced_analytics: bool = True,
        kg_algorithms: bool = True,
        vector_store_features: bool = True,
        evaluators: Optional[List[str]] = None,
        eval_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize AgentContext with optional advanced features.

        Args:
            vector_store: Vector store instance (required)
            knowledge_graph: Knowledge graph instance (optional, enables GraphRAG)
            retention_days: Days to keep memories (default: 30, None=unlimited)
            max_memories: Maximum number of memories (default: 10000)
            graph_expansion: Enable graph expansion for retrieval (default: True)
            max_expansion_hops: Maximum hops for graph expansion (default: 2)
            hybrid_alpha: Balance between vector (0) and graph (1) retrieval
                (default: 0.5)
            decision_tracking: Enable decision tracking features (default: False)
            advanced_analytics: Enable advanced analytics (default: True)
            kg_algorithms: Enable KG algorithms integration (default: True)
            vector_store_features: Enable vector store features (default: True)
            evaluators: Optional list of semantica.evals evaluator names run
                automatically on every recorded decision (graph_store decision
                backend only). Passed through to DecisionRecorder; see its
                docstring. Omitting this leaves record_decision() unchanged.
            eval_config: Optional semantica.evals config dict, keyed by
                evaluator name, passed through to DecisionRecorder.
            **kwargs: Additional options passed to underlying components

        Raises:
            ValueError: If vector_store is not provided
        """
        self.logger = get_logger("agent_context")

        if vector_store is None:
            raise ValueError(
                "vector_store is required for AgentContext. "
                "Please provide a vector store instance. "
                "Example: AgentContext(vector_store=your_vector_store)"
            )

        self.vector_store = vector_store
        self.knowledge_graph = knowledge_graph
        self._checkpoints: Dict[str, Dict[str, Any]] = {}
        self._temporal_version_manager = kwargs.get("temporal_version_manager")
        self.evaluators = evaluators
        self.eval_config = eval_config or {}

        # Store advanced feature flags
        self.config = {
            "decision_tracking": decision_tracking,
            "advanced_analytics": advanced_analytics,
            "kg_algorithms": kg_algorithms,
            "vector_store_features": vector_store_features,
            "graph_expansion": graph_expansion,
            "max_expansion_hops": max_expansion_hops,
            "hybrid_alpha": hybrid_alpha,
            **kwargs
        }

        # Initialize AgentMemory
        retention_policy = f"{retention_days}_days" if retention_days else "unlimited"
        memory_config = {
            "vector_store": vector_store,
            "knowledge_graph": knowledge_graph,
            "retention_policy": retention_policy,
            "max_memory_size": max_memories,
            **kwargs,
        }
        self._memory = AgentMemory(**memory_config)

        # Initialize ContextRetriever if knowledge_graph available
        if knowledge_graph:
            retriever_config = {
                "memory_store": self._memory,
                "knowledge_graph": knowledge_graph,
                "vector_store": vector_store,
                "use_graph_expansion": graph_expansion,
                "max_expansion_hops": max_expansion_hops,
                "hybrid_alpha": hybrid_alpha,
                **kwargs,
            }
            self._retriever = ContextRetriever(**retriever_config)
        else:
            self._retriever = None

        # Initialize graph builder if knowledge graph supports building
        self._graph_builder = None
        if knowledge_graph and hasattr(knowledge_graph, "build_from_conversations"):
            self._graph_builder = knowledge_graph

        self.config.update({
            "retention_days": retention_days,
            "max_memories": max_memories,
        })
        
        # Initialize decision tracking components if enabled
        self._decision_backend = None
        self._decision_recorder = None
        self._decision_query = None
        self._causal_analyzer = None
        self._policy_engine = None
        
        if decision_tracking and knowledge_graph:
            if hasattr(knowledge_graph, "execute_query"):
                self._decision_backend = "graph_store"
                try:
                    self._decision_recorder = DecisionRecorder(
                        knowledge_graph,
                        evaluators=self.evaluators,
                        eval_config=self.eval_config,
                    )
                    self._decision_query = DecisionQuery(
                        graph_store=knowledge_graph,
                        vector_store=vector_store if vector_store_features else None,
                        advanced_analytics=advanced_analytics,
                        centrality_analysis=kg_algorithms,
                        community_detection=kg_algorithms,
                        node_embeddings=kg_algorithms
                    )
                    self._causal_analyzer = CausalChainAnalyzer(knowledge_graph)
                    self._policy_engine = PolicyEngine(knowledge_graph)
                    self.logger.info("Enhanced decision tracking components initialized successfully")
                except Exception as e:
                    self.logger.warning(
                        f"Failed to initialize enhanced decision tracking ({type(e).__name__})"
                    )
                    self._decision_recorder = DecisionRecorder(
                        knowledge_graph,
                        evaluators=self.evaluators,
                        eval_config=self.eval_config,
                    )
                    self._decision_query = DecisionQuery(knowledge_graph)
                    self._causal_analyzer = CausalChainAnalyzer(knowledge_graph)
                    self._policy_engine = PolicyEngine(knowledge_graph)
            else:
                self._decision_backend = "context_graph"
                # Initialize basic decision components for ContextGraph
                self._policy_engine = PolicyEngine(knowledge_graph)
                self._causal_analyzer = CausalChainAnalyzer(knowledge_graph)
                
                # Initialize DecisionQuery for ContextGraph
                try:
                    self._decision_query = DecisionQuery(
                        graph_store=knowledge_graph,
                        vector_store=vector_store if vector_store_features else None,
                        advanced_analytics=advanced_analytics,
                        centrality_analysis=kg_algorithms,
                        community_detection=kg_algorithms,
                        node_embeddings=kg_algorithms
                    )
                    self.logger.info("ContextGraph decision tracking initialized successfully")
                except Exception as e:
                    self.logger.warning(
                        f"Failed to initialize DecisionQuery for ContextGraph ({type(e).__name__})"
                    )
                    # Create a minimal DecisionQuery that delegates to ContextGraph
                    self._decision_query = type('MinimalDecisionQuery', (), {
                        'analyze_decision_influence': lambda self, decision_id, max_depth=3: 
                            knowledge_graph.analyze_decision_influence(decision_id, max_depth) if hasattr(knowledge_graph, 'analyze_decision_influence') else {},
                        'find_precedents': lambda self, query, category=None, limit=10:
                            knowledge_graph.find_precedents(query, category, limit) if hasattr(knowledge_graph, 'find_precedents') else [],
                    })()
                
                if vector_store_features and hasattr(self.vector_store, "initialize_decision_pipeline"):
                    try:
                        self.vector_store.initialize_decision_pipeline(
                            graph_store=knowledge_graph if kg_algorithms else None,
                            use_graph_features=kg_algorithms
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to initialize decision pipeline ({type(e).__name__})"
                        )

    @property
    def memory(self) -> AgentMemory:
        """Access underlying AgentMemory instance."""
        return self._memory

    @property
    def retriever(self) -> Optional[ContextRetriever]:
        """Access underlying ContextRetriever instance."""
        return self._retriever

    @property
    def graph_builder(self) -> Optional[Any]:
        """Access underlying ContextGraph instance for building."""
        return self._graph_builder

    def save(self, path: str) -> None:
        """
        Save context state (memory, vector store, graph) to disk.

        Args:
            path: Directory path to save to
        """
        import os

        os.makedirs(path, exist_ok=True)

        # 1. Save AgentMemory state
        if hasattr(self._memory, "save"):
            self._memory.save(path)

        # 2. Save VectorStore state
        if hasattr(self.vector_store, "save"):
            vs_path = os.path.join(path, "vector_store")
            self.vector_store.save(vs_path)

        # 3. Save Knowledge Graph state
        if self.knowledge_graph:
            if hasattr(self.knowledge_graph, "save_to_file"):
                # JSON export for ContextGraph
                kg_path = os.path.join(path, "knowledge_graph.json")
                self.knowledge_graph.save_to_file(kg_path)
            elif hasattr(self.knowledge_graph, "save"):
                # Generic save
                kg_path = os.path.join(path, "knowledge_graph")
                self.knowledge_graph.save(kg_path)

        self.logger.info(f"Saved agent context to {path}")

    def load(self, path: str) -> None:
        """
        Load context state from disk.

        Args:
            path: Directory path to load from
        """
        import os

        if not os.path.exists(path):
            self.logger.warning(f"Context path not found: {path}")
            return

        # 1. Load AgentMemory state
        if hasattr(self._memory, "load"):
            self._memory.load(path)

        # 2. Load VectorStore state
        if hasattr(self.vector_store, "load"):
            vs_path = os.path.join(path, "vector_store")
            if os.path.exists(vs_path):
                self.vector_store.load(vs_path)

        # 3. Load Knowledge Graph state
        if self.knowledge_graph:
            kg_json_path = os.path.join(path, "knowledge_graph.json")
            kg_dir_path = os.path.join(path, "knowledge_graph")

            if hasattr(self.knowledge_graph, "load_from_file") and os.path.exists(
                kg_json_path
            ):
                self.knowledge_graph.load_from_file(kg_json_path)
            elif hasattr(self.knowledge_graph, "load") and os.path.exists(kg_dir_path):
                self.knowledge_graph.load(kg_dir_path)

        self.logger.info(f"Loaded agent context from {path}")

    def store(
        self,
        content: Union[str, List[str], List[Dict[str, Any]]],
        metadata: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        extract_entities: bool = True,
        extract_relationships: bool = True,
        link_entities: bool = True,
        auto_extract: bool = False,
        **kwargs,
    ) -> Union[str, Dict[str, Any]]:
        """
        Store content (memory or documents).

        Auto-detects content type:
        - Single string -> Memory item
        - List of strings/dicts -> Documents (builds graph if knowledge_graph available)

        Args:
            content: Content to store:
                - str: Single memory item
                - List[str]: Multiple documents
                - List[Dict]: Documents with metadata
            metadata: Additional metadata dict
            conversation_id: Conversation ID (for memories)
            user_id: User ID (for memories)
            entities: Pre-extracted entities (optional)
            relationships: Pre-extracted relationships (optional)
            extract_entities: Extract entities from documents (default: True)
            extract_relationships: Extract relationships (default: True)
            link_entities: Link entities across documents (default: True)
            auto_extract: Auto-extract entities/relationships if not provided
                (default: False)
            **kwargs: Additional options passed to storage methods

        Returns:
            - str: Memory ID (for single memory)
            - Dict: Statistics (for documents) with stored_count, graph_nodes,
              graph_edges

        Example:
            >>> # Store memory
            >>> memory_id = context.store("User likes Python", conversation_id="conv1")

            >>> # Store documents
            >>> stats = context.store(["Doc 1", "Doc 2"], extract_entities=True)
        """
        # Auto-detect content type
        if isinstance(content, str):
            # Single memory item
            memory_metadata = metadata or {}
            if conversation_id:
                memory_metadata["conversation_id"] = conversation_id
            if user_id:
                memory_metadata["user_id"] = user_id

            return self._memory.store(
                content,
                metadata=memory_metadata,
                entities=entities,
                relationships=relationships,
                **kwargs,
            )

        elif isinstance(content, list):
            # Documents - normalize to list of dicts
            documents = self._normalize_documents(content)

            # Add entities/relationships to documents if provided
            if entities or relationships:
                for doc in documents:
                    if entities and "entities" not in doc:
                        doc["entities"] = entities
                    if relationships and "relationships" not in doc:
                        doc["relationships"] = relationships

            # Store each document in vector store
            stored_ids = []
            for doc in documents:
                doc_metadata = {**(metadata or {}), **doc.get("metadata", {})}
                doc_entities = doc.get("entities")
                doc_relationships = doc.get("relationships")

                doc_id = self._memory.store(
                    doc["content"],
                    metadata=doc_metadata,
                    entities=doc_entities,
                    relationships=doc_relationships,
                    **kwargs,
                )
                stored_ids.append(doc_id)

            # Build graph if knowledge_graph available and flags set
            graph_stats = {}
            if self.knowledge_graph and (
                extract_entities or extract_relationships or auto_extract
            ):
                graph_stats = self._build_graph_from_documents(
                    documents,
                    extract_entities=extract_entities or auto_extract,
                    extract_relationships=extract_relationships or auto_extract,
                    link_entities=link_entities,
                )

            return {
                "stored_count": len(stored_ids),
                "memory_ids": stored_ids,
                "graph_nodes": graph_stats.get("node_count", 0),
                "graph_edges": graph_stats.get("edge_count", 0),
            }

        else:
            raise ValueError(
                f"Unsupported content type: {type(content)}. "
                "Expected str (single memory) or list (multiple documents). "
                f"Received: {type(content).__name__}"
            )

    def retrieve(
        self,
        query: str,
        max_results: int = 5,
        use_graph: Optional[bool] = None,
        min_score: float = 0.0,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        include_entities: bool = True,
        include_relationships: bool = False,
        expand_graph: bool = True,
        deduplicate: bool = True,
        anchor_node: Optional[str] = None,
        max_hops: Optional[int] = None,
        proximity_weight: float = 0.0,
        min_confidence_decay: float = 0.0,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context.

        Auto-detects best strategy:
        - If knowledge_graph available -> GraphRAG (hybrid retrieval)
        - Otherwise -> Simple RAG (vector only)

        Args:
            query: Search query
            max_results: Maximum results (default: 5)
            use_graph: Force graph usage (None=auto-detect, True=force,
                False=vector only)
            min_score: Minimum relevance score (default: 0.0)
            conversation_id: Filter by conversation ID
            user_id: Filter by user ID
            include_entities: Include related entities in results (default: True)
            include_relationships: Include relationships in results (default: False)
            expand_graph: Use graph expansion (default: True)
            deduplicate: Deduplicate results (default: True)
            **kwargs: Additional filters (type, date_range, etc.)

        Returns:
            List of context dicts with content, score, source, and metadata

        Example:
            >>> # Auto-detects RAG vs GraphRAG
            >>> results = context.retrieve("Python programming")

            >>> # Force vector-only retrieval
            >>> results = context.retrieve("Python", use_graph=False)
        """
        # Auto-detect strategy
        if use_graph is None:
            use_graph = self.knowledge_graph is not None and self._retriever is not None

        # Apply filters if provided
        if conversation_id:
            kwargs["conversation_id"] = conversation_id
        if user_id:
            kwargs["user_id"] = user_id

        if use_graph and self._retriever:
            # GraphRAG: Use ContextRetriever (hybrid retrieval)
            results = self._retriever.retrieve(
                query,
                max_results=max_results,
                use_graph_expansion=expand_graph,
                min_relevance_score=min_score,
                **kwargs,
            )
            # Convert RetrievedContext to dicts
            result_dicts = [
                self._context_to_dict(r, include_entities, include_relationships)
                for r in results
            ]
            return self._apply_proximity_metadata(
                result_dicts,
                anchor_node=anchor_node,
                max_hops=max_hops,
                proximity_weight=proximity_weight,
                min_confidence_decay=min_confidence_decay,
                max_results=max_results,
            )
        else:
            # Simple RAG: Use AgentMemory (vector + memory)
            results = self._memory.retrieve(
                query, max_results=max_results, min_score=min_score, **kwargs
            )
            # Convert to dicts
            result_dicts = [self._memory_to_dict(r) for r in results]
            return self._apply_proximity_metadata(
                result_dicts,
                anchor_node=anchor_node,
                max_hops=max_hops,
                proximity_weight=proximity_weight,
                min_confidence_decay=min_confidence_decay,
                max_results=max_results,
            )

    def query_with_reasoning(
        self,
        query: str,
        llm_provider: Any,
        max_results: int = 10,
        max_hops: int = 2,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Query with multi-hop reasoning and LLM-based response generation.

        Retrieves context, builds reasoning paths through the graph, and generates
        a natural language response grounded in the knowledge graph.

        Args:
            query: User query
            llm_provider: LLM provider instance (from semantica.llms)
            max_results: Maximum context results to retrieve (default: 10)
            max_hops: Maximum graph traversal hops (default: 2)
            **kwargs: Additional retrieval options

        Returns:
            Dictionary with:
                - response: Generated natural language answer
                - reasoning_path: Multi-hop reasoning trace
                - sources: Retrieved context items
                - confidence: Overall confidence score

        Example:
            >>> from semantica.llms import Groq
            >>> llm = Groq(model="llama-3.1-8b-instant")
            >>> result = context.query_with_reasoning(
            ...     "What IPs are associated with security alerts?",
            ...     llm_provider=llm,
            ...     max_hops=2
            ... )
            >>> print(result['response'])
        """
        if not self._retriever:
            # Fallback if retriever not available
            return {
                "response": "GraphRAG retriever not available. Please configure knowledge_graph.",
                "reasoning_path": "",
                "sources": [],
                "confidence": 0.0,
                "num_sources": 0,
                "num_reasoning_paths": 0
            }

        # Delegate to ContextRetriever
        return self._retriever.query_with_reasoning(
            query=query,
            llm_provider=llm_provider,
            max_results=max_results,
            max_hops=max_hops,
            **kwargs
        )

    def forget(
        self,
        memory_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        days_old: Optional[int] = None,
        **filters,
    ) -> int:
        """
        Delete memories.

        Args:
            memory_id: Delete specific memory by ID
            conversation_id: Delete all memories in conversation
            user_id: Delete all memories for user
            days_old: Delete memories older than N days
            **filters: Additional filters (type, date_range, etc.)

        Returns:
            Number of memories deleted

        Example:
            >>> context.forget(memory_id="mem123")
            >>> context.forget(conversation_id="conv1")
            >>> context.forget(days_old=90)
        """
        if memory_id:
            self._memory.delete_memory(memory_id)
            return 1

        # Build filters dict
        filter_dict = {}
        if conversation_id:
            filter_dict["conversation_id"] = conversation_id
        if user_id:
            filter_dict["user_id"] = user_id
        if days_old:
            from datetime import datetime, timedelta

            filter_dict["start_date"] = (
                datetime.now() - timedelta(days=days_old)
            ).isoformat()
        filter_dict.update(filters)

        return self._memory.clear_memory(**filter_dict)

    def conversation(
        self,
        conversation_id: str,
        max_items: int = 100,
        reverse: bool = False,
        include_metadata: bool = True,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history.

        Args:
            conversation_id: Conversation ID
            max_items: Maximum items to return (default: 100)
            reverse: Return in reverse chronological order (default: False)
            include_metadata: Include full metadata (default: True)
            **kwargs: Additional options

        Returns:
            List of memory dicts in conversation

        Example:
            >>> history = context.conversation("conv1")
            >>> history = context.conversation(
            ...     "conv1", reverse=True, include_metadata=False
            ... )
        """
        history = self._memory.get_conversation_history(
            conversation_id=conversation_id, max_items=max_items
        )

        # Convert to dicts
        result = []
        for item in history:
            item_dict = {
                "id": item.get("id"),
                "content": item.get("content"),
                "timestamp": item.get("timestamp"),
            }
            if include_metadata:
                item_dict["metadata"] = item.get("metadata", {})
            result.append(item_dict)

        if reverse:
            result.reverse()

        return result

    def _normalize_documents(
        self, content: List[Union[str, Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Normalize documents to list of dicts."""
        documents = []
        for i, doc in enumerate(content):
            if isinstance(doc, str):
                documents.append({"content": doc, "id": f"doc_{i}", "metadata": {}})
            elif isinstance(doc, dict):
                if "content" not in doc:
                    raise ValueError(f"Document dict must have 'content' key: {doc}")

                doc_dict = {
                    "content": doc["content"],
                    "id": doc.get("id", f"doc_{i}"),
                    "metadata": doc.get("metadata", {}),
                }

                # Preserve entities and relationships if present
                if "entities" in doc:
                    doc_dict["entities"] = doc["entities"]
                if "relationships" in doc:
                    doc_dict["relationships"] = doc["relationships"]

                documents.append(doc_dict)
            else:
                raise ValueError(f"Unsupported document type: {type(doc)}")
        return documents

    def _build_graph_from_documents(
        self,
        documents: List[Dict[str, Any]],
        extract_entities: bool = True,
        extract_relationships: bool = True,
        link_entities: bool = True,
    ) -> Dict[str, Any]:
        """Build graph from documents."""
        if not self._graph_builder:
            return {"node_count": 0, "edge_count": 0}

        try:
            # Convert documents to conversations format
            conversations = []
            for doc in documents:
                conv = {
                    "id": doc.get("id", "unknown"),
                    "content": doc["content"],
                    "entities": doc.get("entities", []),
                    "relationships": doc.get("relationships", []),
                }
                conversations.append(conv)

            # Build graph from conversations
            graph = self._graph_builder.build_from_conversations(
                conversations,
                link_entities=link_entities,
                extract_intents=False,
                extract_sentiments=False,
            )

            return {
                "node_count": graph.get("statistics", {}).get("node_count", 0),
                "edge_count": graph.get("statistics", {}).get("edge_count", 0),
            }
        except Exception as e:
            self.logger.warning(f"Failed to build graph from documents ({type(e).__name__})")
            return {"node_count": 0, "edge_count": 0}

    def _context_to_dict(
        self,
        context: RetrievedContext,
        include_entities: bool = True,
        include_relationships: bool = False,
    ) -> Dict[str, Any]:
        """Convert RetrievedContext to dict."""
        result = {
            "content": context.content,
            "score": context.score,
            "source": context.source,
            "metadata": context.metadata,
        }

        if include_entities:
            result["related_entities"] = context.related_entities

        if include_relationships:
            result["related_relationships"] = context.related_relationships

        return result

    def _apply_proximity_metadata(
        self,
        results: List[Dict[str, Any]],
        anchor_node: Optional[str] = None,
        max_hops: Optional[int] = None,
        proximity_weight: float = 0.0,
        min_confidence_decay: float = 0.0,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Enrich retrieval results with graph distance from an anchor node."""
        if not anchor_node or not self.knowledge_graph:
            return results
        if not hasattr(self.knowledge_graph, "get_neighbor_distances"):
            return results

        search_hops = max_hops if max_hops is not None else 10
        distances = self.knowledge_graph.get_neighbor_distances(
            anchor_node,
            hops=search_hops,
            min_confidence=min_confidence_decay,
        )
        by_node_id = {item.get("id"): item for item in distances}
        if anchor_node:
            by_node_id[anchor_node] = {
                "id": anchor_node,
                "hop": 0,
                "confidence_decay": 1.0,
                "distance_band": "direct",
                "path_to_anchor": [anchor_node],
            }

        enriched: List[Dict[str, Any]] = []
        for result in results:
            metadata = result.get("metadata") or {}
            result_id = (
                result.get("id")
                or metadata.get("node_id")
                or metadata.get("id")
                or metadata.get("memory_id")
            )
            distance = by_node_id.get(result_id)
            if not distance:
                if max_hops is not None or min_confidence_decay > 0.0:
                    continue
                enriched.append(result)
                continue

            hop_distance = distance.get("hop")
            if max_hops is not None and hop_distance is not None and hop_distance > max_hops:
                continue

            proximity_score = 1.0 if hop_distance == 0 else 1.0 / float(hop_distance or 1)
            score = float(result.get("score", 0.0))
            bounded_weight = min(max(float(proximity_weight), 0.0), 1.0)
            combined_score = (1.0 - bounded_weight) * score + bounded_weight * proximity_score
            enriched_result = {
                **result,
                "graph_node_id": result_id,
                "hop_distance": hop_distance,
                "confidence_decay": distance.get("confidence_decay"),
                "distance_band": distance.get("distance_band"),
                "path_to_anchor": distance.get("path_to_anchor"),
                "proximity_score": proximity_score,
                "combined_score": combined_score,
            }
            enriched.append(enriched_result)

        if proximity_weight > 0:
            enriched.sort(key=lambda item: item.get("combined_score", item.get("score", 0.0)), reverse=True)
        return enriched[:max_results] if max_results is not None else enriched

    def _memory_to_dict(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Convert memory result to dict."""
        return {
            "content": memory.get("content", ""),
            "score": memory.get("score", 0.0),
            "source": "memory",
            "metadata": memory.get("metadata", {}),
            "related_entities": [],
            "related_relationships": [],
        }

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory dict or None if not found

        Example:
            >>> memory = context.get_memory("mem123")
        """
        memory_item = self._memory.get_memory(memory_id)
        if memory_item:
            return {
                "id": memory_item.get("id"),
                "content": memory_item.get("content"),
                "timestamp": memory_item.get("timestamp"),
                "metadata": memory_item.get("metadata", {}),
            }
        return None

    def stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored memories.

        Returns:
            Dict with statistics: total_items, items_by_type, etc.

        Example:
            >>> stats = context.stats()
            >>> print(f"Total memories: {stats['total_items']}")
        """
        return self._memory.get_statistics()

    def link(
        self,
        text: str,
        entities: Optional[List[Dict[str, Any]]] = None,
        similarity_threshold: float = 0.8,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Link entities in text (if knowledge_graph available).

        Args:
            text: Text containing entities
            entities: List of entities to link
            similarity_threshold: Similarity threshold for linking (default: 0.8)
            **kwargs: Additional options

        Returns:
            List of linked entity dicts

        Raises:
            ValueError: If knowledge_graph not available

        Example:
            >>> linked = context.link("Python is used for ML", entities=[...])
        """
        if not self.knowledge_graph:
            raise ValueError(
                "knowledge_graph is required for entity linking. "
                "Please initialize AgentContext with a knowledge_graph parameter. "
                "Example: AgentContext(vector_store=vs, knowledge_graph=kg)"
            )

        linker = EntityLinker(
            knowledge_graph=self.knowledge_graph,
            similarity_threshold=similarity_threshold,
            **kwargs,
        )

        linked_entities = linker.link(text, entities=entities or [])

        return [
            {
                "entity_id": e.entity_id,
                "uri": e.uri,
                "text": e.text,
                "type": e.type,
                "linked_count": len(e.linked_entities),
                "confidence": e.confidence,
            }
            for e in linked_entities
        ]

    def build_graph(
        self,
        entities: Optional[List[Dict[str, Any]]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        conversations: Optional[List[Dict[str, Any]]] = None,
        link_entities: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Build context graph from entities, relationships, or conversations.

        Args:
            entities: List of entities
            relationships: List of relationships
            conversations: List of conversations
            link_entities: Link entities (default: True)
            **kwargs: Additional options

        Returns:
            Graph statistics dict

        Raises:
            ValueError: If knowledge_graph not available

        Example:
            >>> graph = context.build_graph(
            ...     entities=entities, relationships=relationships
            ... )
        """
        if not self._graph_builder:
            raise ValueError(
                "knowledge_graph is required for graph building. "
                "Please initialize AgentContext with a knowledge_graph parameter. "
                "Example: AgentContext(vector_store=vs, knowledge_graph=kg)"
            )

        if entities and relationships:
            graph = self._graph_builder.build_from_entities_and_relationships(
                entities, relationships, **kwargs
            )
        elif conversations:
            graph = self._graph_builder.build_from_conversations(
                conversations, link_entities=link_entities, **kwargs
            )
        else:
            raise ValueError(
                "Must provide either (entities and relationships) or conversations. "
                f"Received: entities={entities is not None}, "
                f"relationships={relationships is not None}, "
                f"conversations={conversations is not None}"
            )

        return graph.get("statistics", {})

    # Memory Management Methods
    def exists(self, memory_id: str) -> bool:
        """
        Check if memory exists.

        Args:
            memory_id: Memory ID to check

        Returns:
            True if memory exists, False otherwise

        Example:
            >>> if context.exists("mem123"):
            ...     print("Memory exists")
        """
        return self._memory.get_memory(memory_id) is not None

    def count(self, **filters) -> int:
        """
        Get total memory count with optional filters.

        Args:
            **filters: Optional filters (conversation_id, user_id, type, etc.)

        Returns:
            Total count of memories matching filters

        Example:
            >>> total = context.count()
            >>> conv_count = context.count(conversation_id="conv1")
        """
        stats = self._memory.get_statistics()
        if not filters:
            return stats.get("total_items", 0)

        # Filter memories
        count = 0
        for memory_id in self._memory.memory_items:
            memory_item = self._memory.memory_items[memory_id]
            if self._memory._matches_filters(memory_item, filters):
                count += 1
        return count

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get memory by ID (alias for get_memory).

        Args:
            memory_id: Memory ID

        Returns:
            Memory dict or None if not found

        Example:
            >>> memory = context.get("mem123")
        """
        return self.get_memory(memory_id)

    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Update existing memory.

        Args:
            memory_id: Memory ID to update
            content: New content (optional)
            metadata: New metadata (optional, merged with existing)
            **kwargs: Additional fields to update

        Returns:
            True if updated successfully, False if not found

        Example:
            >>> context.update("mem123", content="Updated content")
            >>> context.update("mem123", metadata={"new_key": "value"})
        """
        memory_item = self._memory.get_memory(memory_id)
        if not memory_item:
            return False

        # Get current values
        current_content = (
            content if content is not None else memory_item.get("content", "")
        )
        current_metadata = memory_item.get("metadata", {})
        if metadata:
            current_metadata.update(metadata)

        # Delete old and create new
        self._memory.delete_memory(memory_id)
        new_id = self._memory.store(
            current_content,
            metadata=current_metadata,
            entities=memory_item.get("entities", []),
            relationships=memory_item.get("relationships", []),
            **kwargs,
        )

        return new_id is not None

    def delete(self, memory_id: str) -> bool:
        """
        Delete memory by ID (alias for forget with memory_id).

        Args:
            memory_id: Memory ID to delete

        Returns:
            True if deleted, False if not found

        Example:
            >>> context.delete("mem123")
        """
        if self.exists(memory_id):
            self._memory.delete_memory(memory_id)
            return True
        return False

    def clear(self, **filters) -> int:
        """
        Clear memories with filters (alias for forget).

        Args:
            **filters: Filter criteria (conversation_id, user_id, days_old, etc.)

        Returns:
            Number of memories deleted

        Example:
            >>> deleted = context.clear(conversation_id="conv1")
            >>> deleted = context.clear(days_old=90)
        """
        return self.forget(**filters)

    def list(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **filters,
    ) -> List[Dict[str, Any]]:
        """
        List memories with pagination.

        Args:
            conversation_id: Filter by conversation ID
            user_id: Filter by user ID
            limit: Maximum items to return (default: 100)
            offset: Number of items to skip (default: 0)
            **filters: Additional filters

        Returns:
            List of memory dicts

        Example:
            >>> memories = context.list(conversation_id="conv1", limit=50)
            >>> memories = context.list(user_id="user123", limit=20, offset=10)
        """
        all_filters = {**filters}
        if conversation_id:
            all_filters["conversation_id"] = conversation_id
        if user_id:
            all_filters["user_id"] = user_id

        results = []
        for memory_id in list(self._memory.memory_items.keys())[
            offset : offset + limit
        ]:
            memory_item = self._memory.memory_items[memory_id]
            if not all_filters or self._memory._matches_filters(
                memory_item, all_filters
            ):
                mem_dict = self._memory.get_memory(memory_id)
                if mem_dict:
                    results.append(mem_dict)

        return results

    def batch_store(self, items: List[Union[str, Dict[str, Any]]]) -> List[str]:
        """
        Store multiple items at once.

        Args:
            items: List of items to store (strings or dicts with content)

        Returns:
            List of memory IDs

        Example:
            >>> ids = context.batch_store(["Item 1", "Item 2", "Item 3"])
        """
        memory_ids = []
        for item in items:
            if isinstance(item, str):
                memory_id = self.store(item)
                memory_ids.append(memory_id)
            elif isinstance(item, dict):
                content = item.get("content", "")
                if content:
                    extra_fields = {
                        k: v
                        for k, v in item.items()
                        if k
                        not in [
                            "content",
                            "metadata",
                            "conversation_id",
                            "user_id",
                        ]
                    }
                    memory_id = self.store(
                        content,
                        metadata=item.get("metadata"),
                        conversation_id=item.get("conversation_id"),
                        user_id=item.get("user_id"),
                        **extra_fields,
                    )
                    memory_ids.append(memory_id)
        return memory_ids

    def batch_delete(self, memory_ids: List[str]) -> int:
        """
        Delete multiple memories.

        Args:
            memory_ids: List of memory IDs to delete

        Returns:
            Number of memories deleted

        Example:
            >>> deleted = context.batch_delete(["mem1", "mem2", "mem3"])
        """
        deleted = 0
        for memory_id in memory_ids:
            if self.delete(memory_id):
                deleted += 1
        return deleted

    def batch_update(self, updates: List[Dict[str, Any]]) -> int:
        """
        Update multiple memories.

        Args:
            updates: List of update dicts with 'memory_id' and fields to update

        Returns:
            Number of memories updated

        Example:
            >>> updated = context.batch_update([
            ...     {"memory_id": "mem1", "content": "New content"},
            ...     {"memory_id": "mem2", "metadata": {"key": "value"}}
            ... ])
        """
        updated = 0
        for update in updates:
            memory_id = update.get("memory_id")
            update_fields = {k: v for k, v in update.items() if k != "memory_id"}
            if memory_id and self.update(memory_id, **update_fields):
                updated += 1
        return updated

    # Search and Retrieval Methods
    def search(self, query: str, **filters) -> List[Dict[str, Any]]:
        """
        Simple search with filters (alias for retrieve).

        Args:
            query: Search query
            **filters: Additional filters (max_results, min_score,
                conversation_id, etc.)

        Returns:
            List of context dicts

        Example:
            >>> results = context.search("Python", max_results=10)
            >>> results = context.search("Python", conversation_id="conv1")
        """
        return self.retrieve(query, **filters)

    def find_similar(
        self, content: str, limit: int = 5, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Find similar content.

        Args:
            content: Content to find similar items for
            limit: Maximum results (default: 5)
            **kwargs: Additional options

        Returns:
            List of similar content dicts

        Example:
            >>> similar = context.find_similar("Python programming", limit=5)
        """
        return self.retrieve(content, max_results=limit, **kwargs)

    def get_context(
        self, query: str, max_results: int = 5, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Get context for query.

        Args:
            query: Query string
            max_results: Maximum results (default: 5)
            **kwargs: Additional options

        Returns:
            List of context dicts

        Example:
            >>> context_data = context.get_context("Python", max_results=10)
        """
        return self.retrieve(query, max_results=max_results, **kwargs)

    def expand_query(
        self, query: str, max_hops: int = 2, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Expand query with graph context.

        Args:
            query: Query string
            max_hops: Maximum graph expansion hops (default: 2)
            **kwargs: Additional options

        Returns:
            List of expanded context dicts

        Example:
            >>> expanded = context.expand_query("Python", max_hops=3)
        """
        if not self._retriever:
            return self.retrieve(query, **kwargs)

        return self.retrieve(
            query, expand_graph=True, max_expansion_hops=max_hops, **kwargs
        )

    # Conversation Methods
    def get_conversation(
        self, conversation_id: str, limit: int = 100, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Get conversation (alias for conversation).

        Args:
            conversation_id: Conversation ID
            limit: Maximum items (default: 100)
            **kwargs: Additional options

        Returns:
            List of conversation memory dicts

        Example:
            >>> conv = context.get_conversation("conv1", limit=50)
        """
        return self.conversation(conversation_id, max_items=limit, **kwargs)

    def list_conversations(
        self, user_id: Optional[str] = None, limit: int = 50
    ) -> List[str]:
        """
        List all conversations.

        Args:
            user_id: Filter by user ID (optional)
            limit: Maximum conversations to return (default: 50)

        Returns:
            List of conversation IDs

        Example:
            >>> conversations = context.list_conversations()
            >>> user_convs = context.list_conversations(user_id="user123")
        """
        conversation_ids = set()
        for memory_id, memory_item in self._memory.memory_items.items():
            conv_id = memory_item.metadata.get("conversation_id")
            if conv_id:
                if user_id is None or memory_item.metadata.get("user_id") == user_id:
                    conversation_ids.add(conv_id)

        return list(conversation_ids)[:limit]

    def delete_conversation(self, conversation_id: str) -> int:
        """
        Delete entire conversation.

        Args:
            conversation_id: Conversation ID to delete

        Returns:
            Number of memories deleted

        Example:
            >>> deleted = context.delete_conversation("conv1")
        """
        return self.forget(conversation_id=conversation_id)

    def conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get conversation summary.

        Args:
            conversation_id: Conversation ID

        Returns:
            Summary dict with count, first_message, last_message, etc.

        Example:
            >>> summary = context.conversation_summary("conv1")
        """
        history = self.conversation(conversation_id, max_items=1000)

        if not history:
            return {
                "conversation_id": conversation_id,
                "message_count": 0,
                "first_message": None,
                "last_message": None,
            }

        return {
            "conversation_id": conversation_id,
            "message_count": len(history),
            "first_message": history[0] if history else None,
            "last_message": history[-1] if history else None,
            "user_id": (
                history[0].get("metadata", {}).get("user_id") if history else None
            ),
        }

    # Export/Import Methods
    def export(
        self, conversation_id: Optional[str] = None, format: str = "json", **filters
    ) -> Union[str, Dict[str, Any]]:
        """
        Export memories.

        Args:
            conversation_id: Export specific conversation (optional)
            format: Export format ('json' or 'dict', default: 'json')
            **filters: Additional filters

        Returns:
            Exported data (JSON string or dict)

        Example:
            >>> data = context.export(conversation_id="conv1")
            >>> data = context.export(format='dict')
        """
        all_filters = {**filters}
        if conversation_id:
            all_filters["conversation_id"] = conversation_id

        memories = self.list(**all_filters)

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "count": len(memories),
            "memories": memories,
        }

        if format == "json":
            import json

            return json.dumps(export_data, indent=2, default=str)
        return export_data

    def import_data(
        self, data: Union[str, Dict[str, Any]], format: str = "json"
    ) -> int:
        """
        Import memories.

        Args:
            data: Data to import (JSON string or dict)
            format: Data format ('json' or 'dict', default: 'json')

        Returns:
            Number of memories imported

        Example:
            >>> imported = context.import_data(json_string)
            >>> imported = context.import_data(data_dict, format='dict')
        """
        if format == "json":
            import json

            if isinstance(data, str):
                data = json.loads(data)

        if not isinstance(data, dict):
            raise ValueError("Invalid data format. Expected dict or JSON string.")

        memories = data.get("memories", [])
        if not memories:
            return 0

        imported = 0
        for memory in memories:
            try:
                memory_id = self.store(
                    memory.get("content", ""),
                    metadata=memory.get("metadata", {}),
                    conversation_id=memory.get("metadata", {}).get("conversation_id"),
                    user_id=memory.get("metadata", {}).get("user_id"),
                )
                if memory_id:
                    imported += 1
            except Exception as e:
                self.logger.warning(f"Failed to import memory ({type(e).__name__})")

        return imported

    def backup(self, **filters) -> str:
        """
        Create backup (alias for export).

        Args:
            **filters: Filter criteria

        Returns:
            JSON string of backup data

        Example:
            >>> backup_data = context.backup()
            >>> backup_data = context.backup(conversation_id="conv1")
        """
        return self.export(format="json", **filters)

    def restore(self, data: Union[str, Dict[str, Any]], format: str = "json") -> int:
        """
        Restore from backup (alias for import_data).

        Args:
            data: Backup data (JSON string or dict)
            format: Data format ('json' or 'dict', default: 'json')

        Returns:
            Number of memories restored

        Example:
            >>> restored = context.restore(backup_data)
        """
        return self.import_data(data, format=format)

    # Statistics and Analytics
    def health(self) -> Dict[str, Any]:
        """
        Check system health.

        Returns:
            Health status dict

        Example:
            >>> health = context.health()
            >>> print(f"Status: {health['status']}")
        """
        stats = self.stats()
        total = stats.get("total_items", 0)

        health_status = {
            "status": "healthy" if total >= 0 else "error",
            "total_memories": total,
            "vector_store_available": self.vector_store is not None,
            "knowledge_graph_available": self.knowledge_graph is not None,
            "retriever_available": self._retriever is not None,
            "graph_builder_available": self._graph_builder is not None,
        }

        return health_status

    # Decision Tracking Methods
    def record_decision(
        self,
        category: str,
        scenario: str,
        reasoning: str,
        outcome: str,
        confidence: float,
        entities: Optional[List[str]] = None,
        cross_system_context: Optional[Dict[str, Any]] = None,
        decision_maker: Optional[str] = "ai_agent",
        valid_from: Optional[Union[str, datetime]] = None,
        valid_until: Optional[Union[str, datetime]] = None,
    ) -> str:
        """
        Record decision (wrapper for DecisionRecorder).
        
        Args:
            category: Decision category
            scenario: Decision scenario
            reasoning: Decision reasoning
            outcome: Decision outcome
            confidence: Confidence score (0-1)
            entities: Optional list of entity IDs
            cross_system_context: Optional cross-system context
            decision_maker: Decision maker identifier
            
        Returns:
            Decision ID
            
        Raises:
            RuntimeError: If decision tracking is not enabled
        """
        if not self._decision_backend:
            raise RuntimeError("Decision tracking is not enabled")
        
        from .decision_models import Decision
        import uuid
        
        decision = Decision(
            decision_id=str(uuid.uuid4()),
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            timestamp=datetime.now(),
            decision_maker=decision_maker or "ai_agent",
            valid_from=valid_from,
            valid_until=valid_until,
        )
        
        entities = entities or []
        source_documents = []  # Could be enhanced to capture source docs

        if self._decision_backend == "graph_store":
            decision_id = self._decision_recorder.record_decision(
                decision, entities, source_documents
            )

            if cross_system_context:
                self._decision_recorder.capture_cross_system_context(
                    decision_id, cross_system_context
                )

            return decision_id

        if not hasattr(self.knowledge_graph, "record_decision"):
            raise RuntimeError("Decision tracking backend does not support decisions")

        # Delegate to ContextGraph
        decision_id = self.knowledge_graph.record_decision(
            category=category,
            scenario=scenario,
            reasoning=reasoning,
            outcome=outcome,
            confidence=confidence,
            entities=entities,
            decision_maker=decision_maker,
            valid_from=valid_from,
            valid_until=valid_until,
            metadata={"cross_system_context": cross_system_context} if cross_system_context else None
        )
        
        return decision_id

    def find_precedents(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: int = 10,
        use_hybrid_search: bool = True,
        max_hops: int = 3,
        include_context: bool = True,
        include_superseded: bool = False,
        as_of: Optional[Union[str, datetime]] = None,
    ) -> List[Decision]:
        """
        Find similar decisions with user controls.
        
        Args:
            scenario: Scenario to find precedents for
            category: Optional category filter
            limit: Maximum number of results
            use_hybrid_search: Use hybrid search (semantic + structural)
            max_hops: Maximum hops for multi-hop reasoning
            include_context: Include full context in results
            
        Returns:
            List of similar decisions
            
        Raises:
            RuntimeError: If decision tracking is not enabled
        """
        if not self._decision_backend:
            raise RuntimeError("Decision tracking is not enabled")

        # Delegate to ContextGraph if available
        if self._decision_backend == "context_graph" and hasattr(self.knowledge_graph, "find_precedents_by_scenario"):
            try:
                precedents = self.knowledge_graph.find_precedents_by_scenario(
                    scenario=scenario,
                    category=category,
                    limit=limit,
                    use_semantic_search=use_hybrid_search,
                    include_superseded=include_superseded,
                    as_of=as_of,
                )
                # Convert to Decision objects if needed
                from .decision_models import Decision
                decisions = []
                for precedent in precedents:
                    decision_data = precedent["decision"]
                    metadata = dict(decision_data.get("metadata", {}) or {})
                    if "entities" in decision_data:
                        metadata["entities"] = decision_data.get("entities", [])
                    decision = Decision(
                        decision_id=decision_data["id"],
                        category=decision_data["category"],
                        scenario=decision_data["scenario"],
                        reasoning=decision_data["reasoning"],
                        outcome=decision_data["outcome"],
                        confidence=decision_data["confidence"],
                        timestamp=datetime.fromtimestamp(decision_data["timestamp"]),
                        decision_maker=decision_data.get("decision_maker"),
                        valid_from=decision_data.get("valid_from"),
                        valid_until=decision_data.get("valid_until"),
                        metadata=metadata,
                    )
                    decisions.append(decision)
                return decisions
            except Exception as e:
                self.logger.exception("ContextGraph find_precedents failed")
                return []

        # Fallback to DecisionQuery for graph_store backend
        if self._decision_backend == "graph_store":
            if use_hybrid_search:
                try:
                    return self._decision_query.find_precedents_hybrid(
                        scenario, category, limit
                    )
                except Exception:
                    return self._decision_query._find_precedents_basic(scenario, category, limit)
            if category:
                return self._decision_query.find_by_category(category, limit)
            return self._decision_query._find_precedents_basic(scenario, category, limit)

        results: List[Decision] = []

        def _safe_parse_timestamp(value: Any) -> datetime:
            if isinstance(value, datetime):
                return value
            if not value:
                return datetime.now()
            try:
                return datetime.fromisoformat(str(value))
            except Exception:
                return datetime.now()

        if use_hybrid_search and hasattr(self.vector_store, "search_decisions"):
            filters = {"category": category} if category else None
            vector_results = self.vector_store.search_decisions(
                query=scenario,
                filters=filters,
                limit=limit,
                use_hybrid_search=True
            )
            for r in vector_results:
                meta = r.get("metadata") or {}
                decision_id = meta.get("decision_id") or meta.get("id")
                if decision_id and hasattr(self.knowledge_graph, "nodes") and decision_id in self.knowledge_graph.nodes:
                    node = self.knowledge_graph.nodes[decision_id]
                    if getattr(node, "node_type", None) == "Decision":
                        data = getattr(node, "properties", {}) or {}
                        decision = Decision(
                            decision_id=decision_id,
                            category=data.get("category", ""),
                            scenario=getattr(node, "content", ""),
                            reasoning=data.get("reasoning", ""),
                            outcome=data.get("outcome", ""),
                            confidence=float(data.get("confidence", 0.0) or 0.0),
                            timestamp=_safe_parse_timestamp(data.get("timestamp")),
                            decision_maker=data.get("decision_maker", "ai_agent"),
                            reasoning_embedding=data.get("reasoning_embedding"),
                            node2vec_embedding=data.get("node2vec_embedding"),
                            metadata={k: v for k, v in data.items() if k not in [
                                "category", "reasoning", "outcome", "confidence",
                                "timestamp", "decision_maker", "reasoning_embedding", "node2vec_embedding"
                            ]}
                        )
                        decision.metadata["score"] = r.get("score")
                        results.append(decision)

        if results:
            return results[:limit]

        if hasattr(self.knowledge_graph, "find_nodes"):
            for node in self.knowledge_graph.find_nodes(node_type="Decision"):
                if category and node.get("metadata", {}).get("category") != category:
                    continue
                data = node.get("metadata", {}) or {}
                results.append(
                    Decision(
                        decision_id=node.get("id", ""),
                        category=data.get("category", ""),
                        scenario=node.get("content", ""),
                        reasoning=data.get("reasoning", ""),
                        outcome=data.get("outcome", ""),
                        confidence=float(data.get("confidence", 0.0) or 0.0),
                        timestamp=_safe_parse_timestamp(data.get("timestamp")),
                        decision_maker=data.get("decision_maker", "ai_agent"),
                        reasoning_embedding=data.get("reasoning_embedding"),
                        node2vec_embedding=data.get("node2vec_embedding"),
                        metadata={k: v for k, v in data.items() if k not in [
                            "category", "reasoning", "outcome", "confidence",
                            "timestamp", "decision_maker", "reasoning_embedding", "node2vec_embedding"
                        ]}
                    )
                )

        return results[:limit]

    def checkpoint(self, label: str) -> Dict[str, Any]:
        """Capture the current context state under a label."""
        snapshot = self._capture_checkpoint_state()
        self._checkpoints[label] = snapshot
        return snapshot

    def diff_checkpoints(self, label1: str, label2: str) -> Dict[str, Any]:
        """Return a structured diff between two named checkpoints."""
        missing = [label for label in (label1, label2) if label not in self._checkpoints]
        if missing:
            raise KeyError(f"Unknown checkpoint label(s): {', '.join(missing)}")

        first = self._checkpoints[label1]
        second = self._checkpoints[label2]

        first_decisions = {decision.get("id"): decision for decision in first.get("decisions", [])}
        second_decisions = {decision.get("id"): decision for decision in second.get("decisions", [])}
        first_relationships = {self._relationship_key(rel): rel for rel in first.get("relationships", [])}
        second_relationships = {self._relationship_key(rel): rel for rel in second.get("relationships", [])}

        return {
            "decisions_added": [second_decisions[key] for key in sorted(set(second_decisions) - set(first_decisions))],
            "decisions_removed": [first_decisions[key] for key in sorted(set(first_decisions) - set(second_decisions))],
            "relationships_added": [second_relationships[key] for key in sorted(set(second_relationships) - set(first_relationships))],
            "relationships_removed": [first_relationships[key] for key in sorted(set(first_relationships) - set(second_relationships))],
        }

    def flush_checkpoint(self, label: str) -> Dict[str, Any]:
        """Persist a named checkpoint via ``TemporalVersionManager``."""
        if label not in self._checkpoints:
            raise KeyError(f"Unknown checkpoint label: {label}")

        if self._temporal_version_manager is None:
            try:
                self._temporal_version_manager = TemporalVersionManager()
            except Exception as exc:
                raise RuntimeError(
                    "flush_checkpoint requires a TemporalVersionManager. "
                    "Pass one via temporal_version_manager= at construction time."
                ) from exc

        return self._temporal_version_manager.create_snapshot(
            self._checkpoints[label],
            version_label=label,
            author=str(self.config.get("checkpoint_author", "agent_context@local.test")),
            description=f"Checkpoint '{label}'",
        )

    def _capture_checkpoint_state(self) -> Dict[str, Any]:
        """Capture a serializable snapshot of the current graph state."""
        if self.knowledge_graph and hasattr(self.knowledge_graph, "state_at"):
            return self.knowledge_graph.state_at(datetime.utcnow())
        if self.knowledge_graph and hasattr(self.knowledge_graph, "to_dict"):
            graph_dict = self.knowledge_graph.to_dict()
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "nodes": graph_dict.get("nodes", []),
                "edges": graph_dict.get("edges", []),
                "entities": graph_dict.get("nodes", []),
                "relationships": graph_dict.get("edges", []),
                "decisions": [
                    {
                        "id": node.get("id"),
                        "category": (node.get("properties", {}) or {}).get("category", ""),
                        "scenario": node.get("content", ""),
                    }
                    for node in graph_dict.get("nodes", [])
                    if str(node.get("type", "")).lower() == "decision"
                ],
            }
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "nodes": [],
            "edges": [],
            "entities": [],
            "relationships": [],
            "decisions": [],
        }

    def _relationship_key(self, relationship: Dict[str, Any]) -> tuple:
        """Build a stable comparison key for checkpoint relationship diffs."""
        return (
            relationship.get("source_id", relationship.get("source")),
            relationship.get("target_id", relationship.get("target")),
            relationship.get("type"),
        )

    def get_causal_chain(
        self,
        decision_id: str,
        direction: str = "upstream",
        max_depth: int = 10
    ) -> List[Decision]:
        """
        Get causal chain (wrapper for CausalChainAnalyzer).
        
        Args:
            decision_id: Decision ID to analyze
            direction: "upstream" (causes) or "downstream" (effects)
            max_depth: Maximum traversal depth
            
        Returns:
            List of decisions in causal chain
            
        Raises:
            RuntimeError: If decision tracking is not enabled
        """
        if not self._decision_backend:
            raise RuntimeError("Decision tracking is not enabled")

        if self._decision_backend == "graph_store":
            return self._causal_analyzer.get_causal_chain(
                decision_id, direction, max_depth
            )

        if self._decision_backend == "context_graph":
            # Use ContextGraph's get_causal_chain method
            if hasattr(self.knowledge_graph, "get_causal_chain"):
                return self.knowledge_graph.get_causal_chain(
                    decision_id=decision_id,
                    direction=direction,
                    max_depth=max_depth
                )
            # Fallback to causal analyzer
            return self._causal_analyzer.get_causal_chain(
                decision_id, direction, max_depth
            )

        if hasattr(self.knowledge_graph, "get_causal_chain"):
            return self.knowledge_graph.get_causal_chain(
                decision_id=decision_id,
                direction=direction,
                max_depth=max_depth
            )

        raise RuntimeError("Decision tracking backend does not support causal chains")

    def get_policy_engine(self) -> PolicyEngine:
        """
        Get PolicyEngine instance.
        
        Returns:
            PolicyEngine instance
            
        Raises:
            RuntimeError: If decision tracking is not enabled
        """
        if not self._policy_engine:
            raise RuntimeError("Decision tracking is not enabled")
        
        return self._policy_engine

    def multi_hop_context_query(
        self,
        start_entity: str,
        query: str,
        max_hops: int = 3
    ) -> Dict[str, Any]:
        """
        Multi-hop reasoning for complex queries.
        
        Args:
            start_entity: Starting entity ID
            query: Query context
            max_hops: Maximum hops to traverse
            
        Returns:
            Query results with context
            
        Raises:
            RuntimeError: If decision tracking is not enabled
        """
        if not self._decision_query:
            raise RuntimeError("Decision tracking is not enabled")
        
        decisions = self._decision_query.multi_hop_reasoning(
            start_entity, query, max_hops
        )
        
        return {
            "query": query,
            "start_entity": start_entity,
            "max_hops": max_hops,
            "decisions": decisions,
            "count": len(decisions)
        }

    def query_decisions(
        self,
        query: str,
        max_hops: int = 3,
        include_context: bool = True,
        use_hybrid_search: bool = True
    ) -> List[Decision]:
        """
        Context-aware queries with user controls.
        
        Args:
            query: Query string
            max_hops: Maximum hops for traversal
            include_context: Include full context
            use_hybrid_search: Use hybrid search
            
        Returns:
            List of relevant decisions
        """
        if not self._decision_query:
            raise RuntimeError("Decision tracking is not enabled")
        
        # For now, use precedent search as decision query
        # Could be enhanced with more sophisticated query parsing
        return self.find_precedents(
            scenario=query,
            limit=50,
            use_hybrid_search=use_hybrid_search,
            max_hops=max_hops
        )

    def trace_decision_explainability(self, decision_id: str) -> Dict[str, Any]:
        """
        Explainable AI with relationship paths.
        
        Args:
            decision_id: Decision ID to trace
            
        Returns:
            Explainability information
        """
        if not self._decision_query:
            raise RuntimeError("Decision tracking is not enabled")
        
        # Get causal chains
        upstream = self.get_causal_chain(decision_id, "upstream", 5)
        downstream = self.get_causal_chain(decision_id, "downstream", 5)
        
        # Trace relationship paths
        relationship_types = ["CAUSED", "INFLUENCED", "PRECEDENT_FOR", "ABOUT"]
        paths = self._decision_query.trace_decision_path(
            decision_id, relationship_types
        )
        
        return {
            "decision_id": decision_id,
            "upstream_decisions": upstream,
            "downstream_decisions": downstream,
            "relationship_paths": paths,
            "total_connections": len(upstream) + len(downstream)
        }

    def capture_cross_system_inputs(
        self,
        systems: List[str],
        entity_id: str
    ) -> Dict[str, Any]:
        """
        Cross-system synthesis.
        
        Args:
            systems: List of system names
            entity_id: Entity ID to capture context for
            
        Returns:
            Cross-system context
        """
        context = {}

        for system in systems:
            captured_at = datetime.now().isoformat()
            payload: Dict[str, Any] = {
                "entity_id": entity_id,
                "system_name": system,
                "captured_at": captured_at,
            }

            try:
                # GraphStore-backed capture path
                if self.knowledge_graph and hasattr(self.knowledge_graph, "execute_query"):
                    query = """
                    MATCH (c:CrossSystemContext {system_name: $system_name})
                    WHERE c.context_data IS NOT NULL
                    RETURN c
                    ORDER BY c.created_at DESC
                    LIMIT 5
                    """
                    result = self.knowledge_graph.execute_query(
                        query, {"system_name": system}
                    )
                    records = result.get("records", []) if isinstance(result, dict) else result
                    payload["status"] = "captured"
                    payload["records_found"] = len(records) if isinstance(records, list) else 0
                    payload["records"] = records if isinstance(records, list) else []
                else:
                    payload["status"] = "captured_without_backend"
                    payload["records_found"] = 0
                    payload["records"] = []
            except Exception as e:
                self.logger.warning(
                    "Cross-system input capture failed for system=%s entity_id=%s: %s",
                    system,
                    entity_id,
                    str(e),
                )
                payload["status"] = "capture_failed"
                payload["error"] = "internal_capture_error"
                payload["records_found"] = 0
                payload["records"] = []

            context[system] = payload
        
        return context

    def usage_stats(self, period: str = "day") -> Dict[str, Any]:
        """
        Get usage statistics.

        Args:
            period: Time period ('day', 'week', 'month', default: 'day')

        Returns:
            Usage statistics dict

        Example:
            >>> usage = context.usage_stats(period='week')
        """
        from datetime import datetime, timedelta

        now = datetime.now()
        if period == "day":
            start = now - timedelta(days=1)
        elif period == "week":
            start = now - timedelta(weeks=1)
        elif period == "month":
            start = now - timedelta(days=30)
        else:
            start = now - timedelta(days=1)

        stats = self.stats()
        total = stats.get("total_items", 0)

        # Count recent memories
        recent_count = 0
        for memory_id, memory_item in self._memory.memory_items.items():
            if memory_item.timestamp >= start:
                recent_count += 1

        return {
            "period": period,
            "total_memories": total,
            "recent_memories": recent_count,
            "conversations": len(self.list_conversations()),
        }
    
    # Enhanced methods for comprehensive context graphs
    def analyze_context_graph(self) -> Dict[str, Any]:
        """
        Analyze the context graph using advanced KG algorithms.
        
        Returns:
            Comprehensive graph analysis results
        """
        if not self._graph_builder or not self.config.get("advanced_analytics", True):
            return {"error": "Advanced analytics not available"}
        
        try:
            # Use the enhanced ContextGraph if available
            if hasattr(self._graph_builder, 'analyze_graph_with_kg'):
                return self._graph_builder.analyze_graph_with_kg()
            else:
                # Fallback to basic analysis
                return {
                    "node_count": len(self._graph_builder.nodes) if hasattr(self._graph_builder, 'nodes') else 0,
                    "edge_count": len(self._graph_builder.edges) if hasattr(self._graph_builder, 'edges') else 0,
                    "message": "Basic analysis only - KG features not available"
                }
        except Exception as e:
            self.logger.error(f"Failed to analyze context graph ({type(e).__name__})")
            return {"error": str(e)}
    
    def find_similar_entities(
        self, entity_id: str, similarity_type: str = "content", top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar entities using advanced similarity measures.
        
        Args:
            entity_id: Reference entity ID
            similarity_type: Type of similarity ("content", "structural", "embedding")
            top_k: Number of similar entities to return
            
        Returns:
            List of dicts with entity ID, content, type, and similarity score
        """
        if not self._graph_builder:
            return []
        
        try:
            if hasattr(self._graph_builder, 'find_similar_nodes'):
                return self._graph_builder.find_similar_nodes(entity_id, similarity_type, top_k)
            else:
                # Fallback to basic content similarity
                return []
        except Exception as e:
            self.logger.error(f"Failed to find similar entities ({type(e).__name__})")
            return []
    
    def get_entity_centrality(self, entity_id: str) -> Dict[str, float]:
        """
        Get centrality measures for an entity.
        
        Args:
            entity_id: Entity ID to analyze
            
        Returns:
            Dictionary of centrality measures
        """
        if not self._graph_builder:
            return {"error": "Graph builder not available"}
        
        try:
            if hasattr(self._graph_builder, 'get_node_centrality'):
                return self._graph_builder.get_node_centrality(entity_id)
            else:
                return {"error": "Centrality analysis not available"}
        except Exception as e:
            self.logger.error(f"Failed to get entity centrality ({type(e).__name__})")
            return {"error": str(e)}
    
    def find_precedents_advanced(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: int = 10,
        use_kg_features: bool = True,
        similarity_weights: Optional[Dict[str, float]] = None,
        anchor_decision_id: Optional[str] = None,
        max_causal_hops: Optional[int] = None,
        min_confidence_decay: float = 0.0,
    ) -> List[Decision]:
        """
        Find precedents using advanced KG and vector store features.
        
        Args:
            scenario: Scenario description
            category: Optional category filter
            limit: Maximum number of results
            use_kg_features: Use KG algorithms if available
            similarity_weights: Weights for different similarity components
            
        Returns:
            List of precedent decisions
        """
        if not self._decision_query:
            raise RuntimeError("Decision tracking is not enabled")
        
        try:
            if hasattr(self._decision_query, 'find_precedents_hybrid'):
                precedents = self._decision_query.find_precedents_hybrid(
                    scenario=scenario,
                    category=category,
                    limit=limit,
                    use_advanced_features=use_kg_features,
                    similarity_weights=similarity_weights
                )
            else:
                # Fallback to basic method
                precedents = self.find_precedents(scenario, category, limit)
            return self._apply_causal_proximity_to_precedents(
                precedents,
                anchor_decision_id=anchor_decision_id,
                max_causal_hops=max_causal_hops,
                min_confidence_decay=min_confidence_decay,
                limit=limit,
            )
        except Exception as e:
            self.logger.error(f"Failed to find advanced precedents ({type(e).__name__})")
            return []

    def _apply_causal_proximity_to_precedents(
        self,
        precedents: List[Decision],
        anchor_decision_id: Optional[str] = None,
        max_causal_hops: Optional[int] = None,
        min_confidence_decay: float = 0.0,
        limit: int = 10,
    ) -> List[Decision]:
        """Attach causal-distance metadata to precedents and optionally filter."""
        if not anchor_decision_id or not self.knowledge_graph:
            return precedents

        causal_types = ["causes", "influences", "leads_to", "supports"]
        max_hops = max_causal_hops if max_causal_hops is not None else 10
        distance_by_id: Dict[str, Dict[str, Any]] = {}
        if hasattr(self.knowledge_graph, "get_neighbor_distances"):
            for item in self.knowledge_graph.get_neighbor_distances(
                anchor_decision_id,
                hops=max_hops,
                relationship_types=causal_types,
                min_confidence=min_confidence_decay,
            ):
                distance_by_id[item.get("id")] = item

        annotated: List[Decision] = []
        for decision in precedents:
            decision_id = getattr(decision, "decision_id", None)
            distance = distance_by_id.get(decision_id)
            if distance is None and hasattr(self.knowledge_graph, "trace_decision_causality"):
                distance = self._distance_from_causality_trace(anchor_decision_id, decision_id, max_hops)

            if distance is None:
                if max_causal_hops is not None or min_confidence_decay > 0.0:
                    continue
                setattr(decision, "causal_hop_distance", None)
                setattr(decision, "path_confidence_decay", None)
                setattr(decision, "distance_band", None)
                annotated.append(decision)
                continue

            hop_distance = distance.get("hop", distance.get("hop_count"))
            confidence_decay = distance.get("confidence_decay")
            if max_causal_hops is not None and hop_distance is not None and hop_distance > max_causal_hops:
                continue
            if confidence_decay is not None and confidence_decay < min_confidence_decay:
                continue

            setattr(decision, "causal_hop_distance", hop_distance)
            setattr(decision, "path_confidence_decay", confidence_decay)
            setattr(decision, "distance_band", distance.get("distance_band"))
            annotated.append(decision)

        annotated.sort(
            key=lambda decision: (
                getattr(decision, "causal_hop_distance", None) is None,
                getattr(decision, "causal_hop_distance", 10**9) or 10**9,
                -(getattr(decision, "path_confidence_decay", 0.0) or 0.0),
            )
        )
        return annotated[:limit]

    def _distance_from_causality_trace(
        self,
        anchor_decision_id: str,
        target_decision_id: Optional[str],
        max_hops: int,
    ) -> Optional[Dict[str, Any]]:
        """Infer anchor-to-target distance from ContextGraph causality reports."""
        if not target_decision_id:
            return None
        try:
            chains = self.knowledge_graph.trace_decision_causality(target_decision_id, max_depth=max_hops)
        except Exception:
            return None
        best: Optional[Dict[str, Any]] = None
        for chain in chains:
            hops = chain.get("hops", chain) if isinstance(chain, dict) else chain
            if not hops:
                continue
            starts_at_anchor = hops[0].get("from") == anchor_decision_id
            ends_at_target = hops[-1].get("to") == target_decision_id
            if starts_at_anchor and ends_at_target:
                candidate = {
                    "hop_count": len(hops),
                    "confidence_decay": chain.get("confidence_decay") if isinstance(chain, dict) else None,
                    "distance_band": chain.get("distance_band") if isinstance(chain, dict) else None,
                }
                if candidate["confidence_decay"] is None:
                    decay = 1.0
                    for hop in hops:
                        decay *= float(hop.get("edge_weight", 1.0))
                    candidate["confidence_decay"] = decay
                if candidate["distance_band"] is None:
                    candidate["distance_band"] = classify_path_distance(candidate["hop_count"])
                if best is None or candidate["hop_count"] < best["hop_count"]:
                    best = candidate
        return best

    def analyze_decision_influence(self, decision_id: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Analyze decision influence using advanced graph algorithms.
        
        Args:
            decision_id: Decision ID to analyze
            max_depth: Maximum depth for influence analysis
            
        Returns:
            Comprehensive influence analysis
        """
        if not self._decision_query:
            raise RuntimeError("Decision tracking is not enabled")
        
        # Delegate to ContextGraph if available
        if hasattr(self.knowledge_graph, "analyze_decision_influence"):
            try:
                return self.knowledge_graph.analyze_decision_influence(decision_id, max_depth)
            except Exception as e:
                self.logger.error(f"ContextGraph analyze_decision_influence failed: {e}")
                # Fallback to DecisionQuery
                pass
        
        # Fallback to DecisionQuery
        try:
            if hasattr(self._decision_query, 'analyze_decision_influence'):
                return self._decision_query.analyze_decision_influence(decision_id, max_depth)
            else:
                # Basic causal chain fallback
                return {
                    "decision_id": decision_id,
                    "downstream_decisions": self.get_causal_chain(decision_id, "downstream", max_depth),
                    "upstream_decisions": self.get_causal_chain(decision_id, "upstream", max_depth),
                    "message": "Basic analysis only - KG features not available"
                }
        except Exception as e:
            self.logger.error(f"Failed to analyze decision influence ({type(e).__name__})")
            return {"error": str(e)}
    
    def predict_decision_relationships(self, decision_id: str, top_k: int = 5) -> List[Dict]:
        """
        Predict potential relationships for a decision.
        
        Args:
            decision_id: Decision ID
            top_k: Number of predictions to return
            
        Returns:
            List of predicted relationships
        """
        if not self._decision_query:
            raise RuntimeError("Decision tracking is not enabled")
        
        try:
            if hasattr(self._decision_query, 'predict_decision_relationships'):
                return self._decision_query.predict_decision_relationships(decision_id, top_k)
            else:
                return []
        except Exception as e:
            self.logger.error(f"Failed to predict decision relationships ({type(e).__name__})")
            return []
    
    def get_context_insights(self) -> Dict[str, Any]:
        """
        Get comprehensive insights about the context graph and decisions.
        
        Returns:
            Dictionary with various insights and metrics
        """
        insights = {
            "timestamp": datetime.now().isoformat(),
            "memory_stats": self.stats(),
            "decision_stats": self.get_decision_statistics() if self.config.get("decision_tracking") and hasattr(self, 'get_decision_statistics') else {},
            "graph_analysis": self.analyze_context_graph(),
            "advanced_features": {
                "kg_algorithms_enabled": self.config.get("kg_algorithms", False),
                "vector_store_features_enabled": self.config.get("vector_store_features", False),
                "decision_tracking_enabled": self.config.get("decision_tracking", False)
            }
        }
        
        return insights
