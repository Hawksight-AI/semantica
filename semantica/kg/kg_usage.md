# Knowledge Graph Module Usage Guide

This guide demonstrates how to use the knowledge graph module for building, analyzing, validating, and managing knowledge graphs, including node embeddings, similarity calculations, path finding, link prediction, temporal knowledge graphs, entity resolution, and graph analytics.

Note: For conflict detection and resolution, use the `semantica.conflicts` module.
For deduplication, use the `semantica.deduplication` module.

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Knowledge Graph Building](#knowledge-graph-building)
3. [Graph Algorithms](#graph-algorithms)
4. [Node Embeddings](#node-embeddings)
5. [Similarity Calculation](#similarity-calculation)
6. [Path Finding](#path-finding)
7. [Link Prediction](#link-prediction)
8. [Centrality Calculation](#centrality-calculation)
9. [Community Detection](#community-detection)
10. [Graph Analysis](#graph-analysis)
11. [Entity Resolution](#entity-resolution)
12. [Connectivity Analysis](#connectivity-analysis)
13. [Temporal Queries](#temporal-queries)
14. [Provenance Tracking](#provenance-tracking)
15. [Using Methods](#using-methods)
16. [Using Registry](#using-registry)
17. [Configuration](#configuration)
18. [Advanced Examples](#advanced-examples)

## Basic Usage

### Using Main Classes

```python
from semantica.kg import GraphBuilder, GraphAnalyzer, NodeEmbedder, SimilarityCalculator, PathFinder, LinkPredictor

# Create graph builder
builder = GraphBuilder(
    merge_entities=True,
    entity_resolution_strategy="fuzzy",
    resolve_conflicts=True
)

# Build knowledge graph
kg = builder.build(sources)

# Analyze graph
analyzer = GraphAnalyzer()
analysis = analyzer.analyze_graph(kg)

# Graph algorithms
embedder = NodeEmbedder()
similarity_calc = SimilarityCalculator()
path_finder = PathFinder()
link_predictor = LinkPredictor()
```


## Knowledge Graph Building

### Basic Graph Building

```python
from semantica.kg import GraphBuilder

# Create graph builder
# Note: resolve_conflicts=True uses the basic resolution capabilities of ConflictDetector.
# For advanced conflict resolution, consider using the semantica.conflicts module directly.
builder = GraphBuilder(
    merge_entities=True,
    entity_resolution_strategy="fuzzy",
    resolve_conflicts=True,
    enable_temporal=False
)

# Build knowledge graph
kg = builder.build(sources)
```

### Temporal Knowledge Graph Building

```python
from semantica.kg import GraphBuilder

# Build temporal knowledge graph
builder = GraphBuilder(
    enable_temporal=True,
    temporal_granularity="day",
    track_history=True,
    version_snapshots=True
)

temporal_kg = builder.build(sources)

# Access temporal information
for rel in temporal_kg["relationships"]:
    if "valid_from" in rel:
        print(f"Relationship valid from: {rel['valid_from']}")
```

### Incremental Building

```python
from semantica.kg import GraphBuilder

builder = GraphBuilder(merge_entities=True)

# Build initial graph
initial_sources = [{"entities": [...], "relationships": [...]}]
kg = builder.build(initial_sources)

# Add more sources incrementally
new_sources = [{"entities": [...], "relationships": [...]}]
updated_kg = builder.build(new_sources)
```

### Building with Different Configurations

```python
from semantica.kg import GraphBuilder

# Default building
builder = GraphBuilder()
kg = builder.build(sources)

# Temporal building
temporal_builder = GraphBuilder(enable_temporal=True)
temporal_kg = temporal_builder.build(sources)

# Incremental building (same builder, multiple calls)
builder = GraphBuilder(merge_entities=True)
kg1 = builder.build(initial_sources)
kg2 = builder.build(additional_sources)
```

### Unknown relation endpoints

When a relationship endpoint names an entity that is absent from the extracted
entity set (for example an LLM/HuggingFace extraction that synthesizes an
endpoint), `GraphBuilder` promotes a synthetic `UNKNOWN` entity so the edge is
not left dangling. This is the default (`"include"`). To drop such
relationships instead, set `unknown_relation_endpoint="reject"`:

```python
builder = GraphBuilder(
    unknown_relation_endpoint="reject",
)
kg = builder.build(sources)  # edges with unknown endpoints are dropped
```

The option can also be set at runtime via the per-module build configuration
(`kg_methods.build.unknown_relation_endpoint`), which is the documented home
for it.

## Graph Algorithms

The knowledge graph module provides advanced algorithms for node embeddings, similarity calculations, path finding, link prediction, centrality measures, and community detection.

### Overview

```python
from semantica.kg import (
    NodeEmbedder, SimilarityCalculator, PathFinder, LinkPredictor,
    CentralityCalculator, CommunityDetector
)

# Initialize algorithms
embedder = NodeEmbedder(method="node2vec")
similarity_calc = SimilarityCalculator(method="cosine")
path_finder = PathFinder(default_algorithm="dijkstra")
link_predictor = LinkPredictor(method="preferential_attachment")
centrality_calc = CentralityCalculator()
community_detector = CommunityDetector()
```

### Algorithm Registry

```python
from semantica.kg import algorithm_registry

# Discover available algorithms
all_algorithms = algorithm_registry.list_all()
print("Available algorithms:", all_algorithms)

# Get algorithm metadata
metadata = algorithm_registry.get_metadata("embeddings", "node2vec")
print("Node2Vec metadata:", metadata)

# Get algorithm capabilities
capabilities = algorithm_registry.get_capabilities("path_finding", "dijkstra")
print("Dijkstra capabilities:", capabilities)
```

## Node Embeddings

Node embeddings capture structural similarity and enable advanced graph analytics using vector representations of nodes.

### Node2Vec Embeddings

```python
from semantica.kg import NodeEmbedder

# Create node embedder with Node2Vec
embedder = NodeEmbedder(
    method="node2vec",
    embedding_dimension=128,
    walk_length=80,
    num_walks=10,
    p=1.0,  # Return parameter
    q=1.0,  # In-out parameter
    workers=1
)

# Compute embeddings for specific node types
embeddings = embedder.compute_embeddings(
    graph_store,
    node_labels=["Entity", "Person"],
    relationship_types=["RELATED_TO", "KNOWS"],
    embedding_dimension=64
)

print(f"Generated embeddings for {len(embeddings)} nodes")
print(f"Embedding dimension: {len(next(iter(embeddings.values())))}")
```

### Customizing Node2Vec Parameters

```python
from semantica.kg import NodeEmbedder

# High-quality embeddings for small graphs
embedder = NodeEmbedder(
    embedding_dimension=256,
    walk_length=100,
    num_walks=20,
    p=2.0,  # More likely to return to previous node
    q=0.5   # Less likely to explore far nodes
)

# Fast embeddings for large graphs
fast_embedder = NodeEmbedder(
    embedding_dimension=64,
    walk_length=40,
    num_walks=5,
    p=0.5,  # Less likely to return
    q=2.0   # More likely to explore
)
```

### Finding Similar Nodes

```python
from semantica.kg import NodeEmbedder

embedder = NodeEmbedder()
embeddings = embedder.compute_embeddings(graph_store, ["Entity"], ["RELATED_TO"])

# Find most similar nodes to a target node
similar_nodes = embedder.find_similar_nodes(
    graph_store,
    target_node="node_123",
    top_k=10
)

print("Most similar nodes:")
for node_id, similarity in similar_nodes:
    print(f"  {node_id}: {similarity:.4f}")
```

### Storing and Retrieving Embeddings

```python
from semantica.kg import NodeEmbedder

embedder = NodeEmbedder()
embeddings = embedder.compute_embeddings(graph_store, ["Entity"], ["RELATED_TO"])

# Store embeddings as node properties
embedder.store_embeddings(graph_store, embeddings, "node2vec_embedding")

# Retrieve embeddings for specific nodes
node_embedding = embedder._get_node_embedding(graph_store, "node_123", "node2vec_embedding")
if node_embedding:
    print(f"Embedding for node_123: {node_embedding[:5]}...")  # First 5 dimensions
```

### Working with Embeddings

```python
import numpy as np
from semantica.kg import NodeEmbedder, SimilarityCalculator

# Compute embeddings
embedder = NodeEmbedder()
embeddings = embedder.compute_embeddings(graph_store, ["Entity"], ["RELATED_TO"])

# Calculate similarities between embeddings
similarity_calc = SimilarityCalculator()

# Batch similarity calculation
query_embedding = embeddings.get("node_123")
similarities = similarity_calc.batch_similarity(embeddings, query_embedding, top_k=5)

print("Most similar nodes to node_123:")
for node_id, similarity in similarities.items():
    print(f"  {node_id}: {similarity:.4f}")
```

## Similarity Calculation

The similarity calculator provides multiple metrics for comparing node embeddings and vectors.

### Cosine Similarity

```python
from semantica.kg import SimilarityCalculator

# Create similarity calculator
similarity_calc = SimilarityCalculator(method="cosine")

# Calculate similarity between two embeddings
embedding1 = [0.1, 0.2, 0.3, 0.4]
embedding2 = [0.2, 0.3, 0.4, 0.5]

similarity = similarity_calc.cosine_similarity(embedding1, embedding2)
print(f"Cosine similarity: {similarity:.4f}")
```

### Multiple Similarity Metrics

```python
from semantica.kg import SimilarityCalculator

similarity_calc = SimilarityCalculator()

# Different similarity metrics
embedding1 = [1.0, 2.0, 3.0]
embedding2 = [2.0, 4.0, 6.0]

cosine_sim = similarity_calc.cosine_similarity(embedding1, embedding2)
euclidean_dist = similarity_calc.euclidean_distance(embedding1, embedding2)
manhattan_dist = similarity_calc.manhattan_distance(embedding1, embedding2)
correlation_sim = similarity_calc.correlation_similarity(embedding1, embedding2)

print(f"Cosine similarity: {cosine_sim:.4f}")
print(f"Euclidean distance: {euclidean_dist:.4f}")
print(f"Manhattan distance: {manhattan_dist:.4f}")
print(f"Correlation similarity: {correlation_sim:.4f}")
```

### Batch Similarity Calculation

```python
from semantica.kg import SimilarityCalculator

similarity_calc = SimilarityCalculator()

# Calculate similarities for multiple embeddings
embeddings = {
    "node1": [0.1, 0.2, 0.3],
    "node2": [0.4, 0.5, 0.6],
    "node3": [0.1, 0.1, 0.1],
    "node4": [0.9, 0.8, 0.7]
}

query_embedding = [0.2, 0.3, 0.4]

# Batch similarity with top-k filtering
similarities = similarity_calc.batch_similarity(
    embeddings, 
    query_embedding, 
    method="cosine",
    top_k=3
)

print("Top 3 most similar nodes:")
for node_id, similarity in similarities.items():
    print(f"  {node_id}: {similarity:.4f}")
```

### Pairwise Similarity Matrix

```python
from semantica.kg import SimilarityCalculator

similarity_calc = SimilarityCalculator()

embeddings = {
    "node1": [1.0, 0.0],
    "node2": [0.0, 1.0],
    "node3": [1.0, 1.0]
}

# Calculate all pairwise similarities
pairwise_similarities = similarity_calc.pairwise_similarity(
    embeddings, 
    method="cosine"
)

print("Pairwise similarities:")
for (node1, node2), similarity in pairwise_similarities.items():
    print(f"  {node1} - {node2}: {similarity:.4f}")
```

### Finding Most Similar Nodes

```python
from semantica.kg import SimilarityCalculator

similarity_calc = SimilarityCalculator()

embeddings = {
    "node1": [0.1, 0.2, 0.3, 0.4],
    "node2": [0.2, 0.3, 0.4, 0.5],
    "node3": [0.9, 0.8, 0.7, 0.6],
    "node4": [0.1, 0.1, 0.1, 0.1]
}

query_embedding = [0.15, 0.25, 0.35, 0.45]

# Find most similar nodes
most_similar = similarity_calc.find_most_similar(
    embeddings, 
    query_embedding, 
    method="cosine",
    top_k=3
)

print("Most similar nodes:")
for node_id, similarity in most_similar:
    print(f"  {node_id}: {similarity:.4f}")
```

## Path Finding

The path finder provides multiple algorithms for finding shortest paths and routes through knowledge graphs.

### Dijkstra's Algorithm

```python
from semantica.kg import PathFinder

# Create path finder
path_finder = PathFinder(default_algorithm="dijkstra")

# Find shortest path using Dijkstra's algorithm
path = path_finder.dijkstra_shortest_path(graph, "source_node", "target_node")

if path:
    print(f"Shortest path: {' -> '.join(path)}")
    print(f"Path length: {len(path) - 1} edges")
else:
    print("No path found")
```

### A* Search with Heuristics

```python
from semantica.kg import PathFinder

path_finder = PathFinder()

# Define heuristic function
def distance_heuristic(node1, node2):
    # Simple heuristic based on node names or positions
    return abs(len(node1) - len(node2))

# Find path using A* search
path = path_finder.a_star_search(
    graph, 
    "source_node", 
    "target_node", 
    heuristic=distance_heuristic
)

print(f"A* path: {' -> '.join(path)}")
```

### BFS for Unweighted Graphs

```python
from semantica.kg import PathFinder

path_finder = PathFinder()

# Find shortest path in unweighted graph using BFS
path = path_finder.bfs_shortest_path(graph, "source_node", "target_node")

print(f"BFS path: {' -> '.join(path)}")
```

### Multiple Shortest Paths

```python
from semantica.kg import PathFinder

path_finder = PathFinder()

# Find all shortest paths from a source node
all_paths = path_finder.all_shortest_paths(graph, "source_node")

for target, paths in all_paths.items():
    print(f"Paths to {target}: {len(paths)}")
    for i, path in enumerate(paths[:3]):  # Show first 3 paths
        print(f"  Path {i+1}: {' -> '.join(path)}")
```

### K-Shortest Paths

```python
from semantica.kg import PathFinder

path_finder = PathFinder()

# Find k shortest paths between two nodes
k_paths = path_finder.find_k_shortest_paths(graph, "source_node", "target_node", k=5)

print(f"Top {len(k_paths)} shortest paths:")
for i, path in enumerate(k_paths):
    length = path_finder.path_length(graph, path)
    print(f"  Path {i+1}: {' -> '.join(path)} (length: {length})")
```

### Path Length Calculation

```python
from semantica.kg import PathFinder

path_finder = PathFinder()

# Calculate path length with custom weights
path = ["A", "B", "C", "D"]
length = path_finder.path_length(
    graph, 
    path, 
    weight_attribute="weight",
    default_weight=1.0
)

print(f"Path length: {length}")
```

### Advanced Path Finding

```python
from semantica.kg import PathFinder

path_finder = PathFinder()

# Find paths with different algorithms
dijkstra_path = path_finder.dijkstra_shortest_path(graph, "A", "Z")
astar_path = path_finder.a_star_search(graph, "A", "Z", lambda x, y: 0)
bfs_path = path_finder.bfs_shortest_path(graph, "A", "Z")

print(f"Dijkstra: {len(dijkstra_path)} steps")
print(f"A* (zero heuristic): {len(astar_path)} steps")
print(f"BFS: {len(bfs_path)} steps")
```

## Link Prediction

Link prediction algorithms identify potential missing connections in knowledge graphs based on various similarity and structural metrics.

### Preferential Attachment

```python
from semantica.kg import LinkPredictor

# Create link predictor
link_predictor = LinkPredictor(method="preferential_attachment")

# Predict potential links
predicted_links = link_predictor.predict_links(
    graph, 
    top_k=10,
    exclude_existing=True
)

print("Top predicted links:")
for node1, node2, score in predicted_links:
    print(f"  {node1} - {node2}: {score:.4f}")
```

### Common Neighbors

```python
from semantica.kg import LinkPredictor

link_predictor = LinkPredictor(method="common_neighbors")

# Predict links based on common neighbors
predicted_links = link_predictor.predict_links(
    graph, 
    method="common_neighbors",
    top_k=10
)

print("Common neighbors predictions:")
for node1, node2, score in predicted_links:
    print(f"  {node1} - {node2}: {score:.4f}")
```

### Advanced Link Prediction Methods

```python
from semantica.kg import LinkPredictor

link_predictor = LinkPredictor()

# Try different prediction methods
methods = ["preferential_attachment", "common_neighbors", "jaccard_coefficient", "adamic_adar"]

for method in methods:
    links = link_predictor.predict_links(graph, method=method, top_k=5)
    print(f"\n{method.replace('_', ' ').title()} predictions:")
    for node1, node2, score in links[:3]:
        print(f"  {node1} - {node2}: {score:.4f}")
```

### Top Links for Specific Node

```python
from semantica.kg import LinkPredictor

link_predictor = LinkPredictor()

# Find top potential connections for a specific node
top_links = link_predictor.predict_top_links(
    graph, 
    source_node="target_node", 
    top_k=10,
    method="preferential_attachment"
)

print(f"Top connections for {source_node}:")
for target_node, score in top_links:
    print(f"  {target_node}: {score:.4f}")
```

### Batch Link Scoring

```python
from semantica.kg import LinkPredictor

link_predictor = LinkPredictor()

# Score specific node pairs
node_pairs = [
    ("node1", "node2"),
    ("node1", "node3"),
    ("node2", "node4")
]

scores = link_predictor.batch_score_links(graph, node_pairs, method="preferential_attachment")

print("Link scores:")
for node1, node2, score in scores:
    print(f"  {node1} - {node2}: {score:.4f}")
```

### Link Prediction with Node Labels

```python
from semantica.kg import LinkPredictor

link_predictor = LinkPredictor()

# Predict links for specific node types
predicted_links = link_predictor.predict_links(
    graph_store,
    node_labels=["Person", "Organization"],
    relationship_types=["WORKS_FOR", "KNOWS"],
    method="common_neighbors",
    top_k=10
)

print("Predicted links between People and Organizations:")
for node1, node2, score in predicted_links:
    print(f"  {node1} - {node2}: {score:.4f}")
```

### Comparative Link Prediction

```python
from semantica.kg import LinkPredictor

link_predictor = LinkPredictor()

# Compare different methods for the same node pair
node1, node2 = "node1", "node2"

methods = ["preferential_attachment", "common_neighbors", "jaccard_coefficient", "adamic_adar"]

print(f"Link prediction scores for {node1} - {node2}:")
for method in methods:
    score = link_predictor.score_link(graph, node1, node2, method=method)
    print(f"  {method}: {score:.4f}")
```

## Graph Analysis

### Comprehensive Analysis

```python
from semantica.kg import GraphAnalyzer

# Create analyzer and analyze graph
analyzer = GraphAnalyzer()
analysis = analyzer.analyze_graph(kg)

print(f"Nodes: {analysis['num_nodes']}")
print(f"Edges: {analysis['num_edges']}")
print(f"Density: {analysis['density']}")
```

### Centrality-Focused Analysis

```python
from semantica.kg import GraphAnalyzer, CentralityCalculator

# Analyze graph with centrality focus
analyzer = GraphAnalyzer()
analysis = analyzer.analyze_graph(kg)

# Calculate centrality separately
centrality_calc = CentralityCalculator()
degree_centrality = centrality_calc.calculate_degree_centrality(kg)

# Access centrality results
if "rankings" in degree_centrality:
    print("Top nodes by degree centrality:")
    for ranking in degree_centrality["rankings"][:5]:
        print(f"  {ranking['node']}: {ranking['score']}")
```

### Community-Focused Analysis

```python
from semantica.kg import CommunityDetector

# Detect communities
detector = CommunityDetector()
result = detector.detect_communities(kg, algorithm="louvain")

# Access community results
if "communities" in result:
    communities = result["communities"]
    print(f"Found {len(communities)} communities")
    for i, community in enumerate(communities):
        print(f"Community {i}: {len(community)} nodes")
```

### Different Types of Analysis

```python
from semantica.kg import GraphAnalyzer, CentralityCalculator, CommunityDetector, ConnectivityAnalyzer

# Default comprehensive analysis
analyzer = GraphAnalyzer()
analysis = analyzer.analyze_graph(kg)

# Centrality analysis
centrality_calc = CentralityCalculator()
centrality = centrality_calc.calculate_all_centrality(kg)

# Community analysis
community_detector = CommunityDetector()
communities = community_detector.detect_communities(kg, algorithm="louvain")

# Connectivity analysis
connectivity_analyzer = ConnectivityAnalyzer()
connectivity = connectivity_analyzer.analyze_connectivity(kg)
```

## Centrality Calculation

The centrality calculator includes PageRank in addition to the traditional centrality measures.

### PageRank Centrality

```python
from semantica.kg import CentralityCalculator

# Create centrality calculator
centrality_calc = CentralityCalculator()

# Calculate PageRank centrality
pagerank_scores = centrality_calc.calculate_pagerank(
    graph,
    max_iterations=100,
    damping_factor=0.85,
    tolerance=1e-6
)

print("PageRank scores:")
for node_id, score in sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {node_id}: {score:.4f}")
```

### PageRank with Custom Parameters

```python
from semantica.kg import CentralityCalculator

centrality_calc = CentralityCalculator()

# High damping factor (more random jumps)
high_damping = centrality_calc.calculate_pagerank(
    graph,
    damping_factor=0.95,
    max_iterations=50
)

# Low damping factor (less random jumps)
low_damping = centrality_calc.calculate_pagerank(
    graph,
    damping_factor=0.5,
    max_iterations=50
)

print("High damping factor top nodes:")
for node_id, score in sorted(high_damping.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {node_id}: {score:.4f}")

print("Low damping factor top nodes:")
for node_id, score in sorted(low_damping.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {node_id}: {score:.4f}")
```

### All Centrality Measures Including PageRank

```python
from semantica.kg import CentralityCalculator

centrality_calc = CentralityCalculator()

# Calculate all centrality measures including PageRank
all_centrality = centrality_calc.calculate_all_centrality(graph)

# Access PageRank results
if "pagerank" in all_centrality["centrality_measures"]:
    pagerank = all_centrality["centrality_measures"]["pagerank"]
    print("Top nodes by PageRank:")
    for ranking in pagerank["rankings"][:5]:
        print(f"  {ranking['node']}: {ranking['score']:.4f}")

# Compare with traditional centrality measures
for measure_type, measure_result in all_centrality["centrality_measures"].items():
    print(f"\n{measure_type.upper()} Centrality:")
    for ranking in measure_result["rankings"][:3]:
        print(f"  {ranking['node']}: {ranking['score']:.4f}")
```

### Centrality Analysis for Specific Node Types

```python
from semantica.kg import CentralityCalculator

centrality_calc = CentralityCalculator()

# Calculate PageRank for specific node labels
pagerank_filtered = centrality_calc.calculate_pagerank(
    graph,
    node_labels=["Person", "Organization"],
    relationship_types=["KNOWS", "WORKS_FOR"]
)

print("PageRank for People and Organizations:")
for node_id, score in sorted(pagerank_filtered.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {node_id}: {score:.4f}")
```

### Traditional Centrality Measures

```python
from semantica.kg import CentralityCalculator

centrality_calc = CentralityCalculator()

# Degree centrality
degree = centrality_calc.calculate_degree_centrality(graph)

# Betweenness centrality
betweenness = centrality_calc.calculate_betweenness_centrality(graph)

# Closeness centrality
closeness = centrality_calc.calculate_closeness_centrality(graph)

# Eigenvector centrality
eigenvector = centrality_calc.calculate_eigenvector_centrality(graph)

print("Traditional centrality measures:")
for measure_name, result in [("Degree", degree), ("Betweenness", betweenness), 
                                 ("Closeness", closeness), ("Eigenvector", eigenvector)]:
    print(f"\n{measure_name} Centrality:")
    for ranking in result["rankings"][:3]:
        print(f"  {ranking['node']}: {ranking['score']:.4f}")
```

## Community Detection

The community detector includes Label Propagation in addition to the existing Louvain and Leiden algorithms.

### Label Propagation Algorithm

```python
from semantica.kg import CommunityDetector

# Create community detector
detector = CommunityDetector()

# Detect communities using Label Propagation
communities = detector.detect_communities_label_propagation(
    graph,
    max_iterations=100,
    random_seed=42
)

print(f"Detected {len(communities['communities'])} communities")
print(f"Algorithm: {communities['algorithm']}")
print(f"Converged in {communities['iterations']} iterations")

# Display community assignments
print("Community assignments:")
for node_id, community_id in communities["node_assignments"].items():
    print(f"  {node_id}: Community {community_id}")
```

### Label Propagation with Custom Parameters

```python
from semantica.kg import CommunityDetector

detector = CommunityDetector()

# Fast community detection (fewer iterations)
fast_communities = detector.detect_communities_label_propagation(
    graph,
    max_iterations=20,
    random_seed=123
)

# High-quality community detection (more iterations)
quality_communities = detector.detect_communities_label_propagation(
    graph,
    max_iterations=200,
    random_seed=456
)

print(f"Fast detection: {len(fast_communities['communities'])} communities")
print(f"Quality detection: {len(quality_communities['communities'])} communities")
```

### Comparing Community Detection Algorithms

```python
from semantica.kg import CommunityDetector

detector = CommunityDetector()

# Compare different algorithms
algorithms = ["louvain", "leiden", "label_propagation"]

for algorithm in algorithms:
    if algorithm == "label_propagation":
        result = detector.detect_communities_label_propagation(graph)
    else:
        result = detector.detect_communities(graph, algorithm=algorithm)
    
    print(f"\n{algorithm.title()} Algorithm:")
    print(f"  Communities: {len(result['communities'])}")
    if 'modularity' in result:
        print(f"  Modularity: {result['modularity']:.4f}")
    if 'iterations' in result:
        print(f"  Iterations: {result['iterations']}")
```

### Community Detection with Node Labels

```python
from semantica.kg import CommunityDetector

detector = CommunityDetector()

# Detect communities for specific node types
communities = detector.detect_communities_label_propagation(
    graph,
    node_labels=["Person", "Organization"],
    relationship_types=["KNOWS", "COLLABORATES_WITH"],
    max_iterations=50
)

print(f"Communities in filtered graph: {len(communities['communities'])}")
```

### Community Metrics and Analysis

```python
from semantica.kg import CommunityDetector

detector = CommunityDetector()

# Detect communities using Label Propagation
communities = detector.detect_communities_label_propagation(graph)

# Calculate community metrics
metrics = detector.calculate_community_metrics(graph, communities)

print(f"Number of communities: {metrics['num_communities']}")
print(f"Average community size: {metrics['avg_community_size']:.2f}")
print(f"Modularity: {metrics.get('modularity', 'N/A')}")

# Analyze community structure
structure = detector.analyze_community_structure(graph, communities)
print(f"Intra-community edges: {structure['intra_community_edges']}")
print(f"Inter-community edges: {structure['inter_community_edges']}")
```

### All Community Detection Methods

```python
from semantica.kg import CommunityDetector

detector = CommunityDetector()

# Louvain algorithm
louvain_result = detector.detect_communities(graph, algorithm="louvain")

# Leiden algorithm
leiden_result = detector.detect_communities(graph, algorithm="leiden", resolution=1.0)

# Label Propagation
label_prop_result = detector.detect_communities_label_propagation(graph, max_iterations=100)

# Overlapping communities
overlapping_result = detector.detect_communities(graph, algorithm="overlapping", k=3)

print("Community Detection Results:")
for name, result in [("Louvain", louvain_result), ("Leiden", leiden_result), 
                           ("Label Propagation", label_prop_result), ("Overlapping", overlapping_result)]:
    print(f"\n{name}:")
    print(f"  Communities: {len(result['communities'])}")
    if 'modularity' in result:
        print(f"  Modularity: {result['modularity']:.4f}")
    if 'iterations' in result:
        print(f"  Iterations: {result['iterations']}")
```

## Entity Resolution

### Fuzzy Matching Resolution

```python
from semantica.kg import EntityResolver

entities = [
    {"id": "1", "name": "Apple Inc.", "type": "Company"},
    {"id": "2", "name": "Apple", "type": "Company"},
    {"id": "3", "name": "Microsoft", "type": "Company"}
]

# Create resolver with fuzzy strategy
resolver = EntityResolver(strategy="fuzzy", similarity_threshold=0.8)
resolved = resolver.resolve_entities(entities)

print(f"Original: {len(entities)} entities")
print(f"Resolved: {len(resolved)} entities")
```

### Exact Matching Resolution

```python
from semantica.kg import EntityResolver

# Exact string matching
resolver = EntityResolver(strategy="exact")
resolved = resolver.resolve_entities(entities)
```

### Semantic Matching Resolution

```python
from semantica.kg import EntityResolver

# Semantic similarity matching
resolver = EntityResolver(strategy="semantic", similarity_threshold=0.9)
resolved = resolver.resolve_entities(entities)
```

### Different Resolution Strategies

```python
from semantica.kg import EntityResolver

# Fuzzy matching
fuzzy_resolver = EntityResolver(strategy="fuzzy", similarity_threshold=0.8)
fuzzy_resolved = fuzzy_resolver.resolve_entities(entities)

# Exact matching
exact_resolver = EntityResolver(strategy="exact")
exact_resolved = exact_resolver.resolve_entities(entities)

# Semantic matching
semantic_resolver = EntityResolver(strategy="semantic", similarity_threshold=0.9)
semantic_resolved = semantic_resolver.resolve_entities(entities)
```

## Centrality Calculation

### Degree Centrality

```python
from semantica.kg import CentralityCalculator

# Calculate degree centrality
calculator = CentralityCalculator()
result = calculator.calculate_degree_centrality(kg)

print("Top nodes by degree centrality:")
for ranking in result["rankings"][:5]:
    print(f"  {ranking['node']}: {ranking['score']}")
```

### Betweenness Centrality

```python
from semantica.kg import CentralityCalculator

# Calculate betweenness centrality
calculator = CentralityCalculator()
result = calculator.calculate_betweenness_centrality(kg)

print("Top nodes by betweenness centrality:")
for ranking in result["rankings"][:5]:
    print(f"  {ranking['node']}: {ranking['score']}")
```

### Closeness Centrality

```python
from semantica.kg import CentralityCalculator

# Calculate closeness centrality
calculator = CentralityCalculator()
result = calculator.calculate_closeness_centrality(kg)

print("Top nodes by closeness centrality:")
for ranking in result["rankings"][:5]:
    print(f"  {ranking['node']}: {ranking['score']}")
```

### Eigenvector Centrality

```python
from semantica.kg import CentralityCalculator

# Calculate eigenvector centrality
calculator = CentralityCalculator()
result = calculator.calculate_eigenvector_centrality(kg)

print("Top nodes by eigenvector centrality:")
for ranking in result["rankings"][:5]:
    print(f"  {ranking['node']}: {ranking['score']}")
```

### All Centrality Measures

```python
from semantica.kg import CentralityCalculator

# Calculate all centrality measures
calculator = CentralityCalculator()
result = calculator.calculate_all_centrality(kg)

for measure_type, measure_result in result["centrality_measures"].items():
    print(f"\n{measure_type.upper()} Centrality:")
    for ranking in measure_result["rankings"][:3]:
        print(f"  {ranking['node']}: {ranking['score']}")
```

## Community Detection

### Louvain Algorithm

```python
from semantica.kg import CommunityDetector

# Detect communities using Louvain algorithm
detector = CommunityDetector()
result = detector.detect_communities(kg, algorithm="louvain")

print(f"Found {len(result['communities'])} communities")
print(f"Modularity: {result['modularity']}")

for i, community in enumerate(result["communities"]):
    print(f"Community {i}: {len(community)} nodes")
```

### Leiden Algorithm

```python
from semantica.kg import CommunityDetector

# Detect communities using Leiden algorithm
detector = CommunityDetector()
result = detector.detect_communities(kg, algorithm="leiden", resolution=1.0)

print(f"Found {len(result['communities'])} communities")
```

### Overlapping Communities

```python
from semantica.kg import CommunityDetector

# Detect overlapping communities
detector = CommunityDetector()
result = detector.detect_communities(kg, algorithm="overlapping", k=3)

print(f"Found {len(result['communities'])} overlapping communities")
print(f"Nodes in multiple communities: {result.get('overlap_count', 0)}")
```

### Community Metrics

```python
from semantica.kg import CommunityDetector

detector = CommunityDetector()
communities = detector.detect_communities(kg, algorithm="louvain")

# Calculate community metrics
metrics = detector.calculate_community_metrics(kg, communities)

print(f"Number of communities: {metrics['num_communities']}")
print(f"Average community size: {metrics['avg_community_size']}")
print(f"Modularity: {metrics['modularity']}")

# Analyze community structure
structure = detector.analyze_community_structure(kg, communities)
print(f"Intra-community edges: {structure['intra_community_edges']}")
print(f"Inter-community edges: {structure['inter_community_edges']}")
```

## Connectivity Analysis

### Comprehensive Connectivity Analysis

```python
from semantica.kg import analyze_connectivity, ConnectivityAnalyzer

# Using convenience function
result = analyze_connectivity(kg, method="default")

print(f"Number of components: {result['num_components']}")
print(f"Is connected: {result['is_connected']}")
print(f"Density: {result['density']}")
print(f"Average degree: {result['avg_degree']}")

# Using class directly
analyzer = ConnectivityAnalyzer()
result = analyzer.analyze_connectivity(kg)
```

### Connected Components

```python
from semantica.kg import analyze_connectivity

# Find connected components
result = analyze_connectivity(kg, method="components")

print(f"Found {result['num_components']} connected components")
for i, component in enumerate(result["components"]):
    print(f"Component {i}: {len(component)} nodes")
```

### Shortest Paths

```python
from semantica.kg import analyze_connectivity, ConnectivityAnalyzer

# Find shortest path between two nodes
result = analyze_connectivity(
    kg,
    method="paths",
    source="node1",
    target="node2"
)

if result["exists"]:
    print(f"Path: {' -> '.join(result['path'])}")
    print(f"Distance: {result['distance']}")
else:
    print("No path found")

# Using class directly
analyzer = ConnectivityAnalyzer()
paths = analyzer.calculate_shortest_paths(kg, source="node1", target="node2")
```

### Bridge Detection

```python
from semantica.kg import analyze_connectivity

# Identify bridge edges
result = analyze_connectivity(kg, method="bridges")

print(f"Found {result['num_bridges']} bridge edges")
for bridge in result["bridge_edges"]:
    print(f"Bridge: {bridge['source']} -> {bridge['target']}")
```

## Temporal Queries

### Time-Point Queries

```python
from semantica.kg import TemporalGraphQuery

# Create query engine and query at specific time
query_engine = TemporalGraphQuery()
result = query_engine.query_at_time(kg, query="", at_time="2024-01-01")

print(f"Entities at time: {result['num_entities']}")
print(f"Relationships at time: {result['num_relationships']}")
```

### Time-Range Queries

```python
from semantica.kg import TemporalGraphQuery

# Query within time range
query_engine = TemporalGraphQuery()
result = query_engine.query_time_range(
    kg,
    query="",
    start_time="2024-01-01",
    end_time="2024-12-31",
    temporal_aggregation="union"
)

print(f"Relationships in range: {result['num_relationships']}")
```

### Temporal Pattern Detection

```python
from semantica.kg import TemporalGraphQuery

# Detect temporal patterns
query_engine = TemporalGraphQuery()
result = query_engine.query_temporal_pattern(kg, pattern="sequence", min_support=2)

print(f"Found {result['num_patterns']} temporal patterns")
```

### Graph Evolution Analysis

```python
from semantica.kg import TemporalGraphQuery

# Analyze graph evolution
query_engine = TemporalGraphQuery()
result = query_engine.analyze_evolution(
    kg,
    start_time="2024-01-01",
    end_time="2024-12-31",
    metrics=["count", "diversity", "stability"]
)

print(f"Relationship count: {result.get('count', 0)}")
print(f"Diversity: {result.get('diversity', 0)}")
print(f"Stability: {result.get('stability', 0)}")
```

### Temporal Path Finding

```python
from semantica.kg import TemporalGraphQuery

query_engine = TemporalGraphQuery()

# Find temporal paths
paths = query_engine.find_temporal_paths(
    kg,
    source="entity1",
    target="entity2",
    start_time="2024-01-01",
    end_time="2024-12-31"
)

print(f"Found {paths['num_paths']} temporal paths")
for path in paths["paths"]:
    print(f"Path: {' -> '.join(path['path'])}")
    print(f"Length: {path['length']}")
```

## Provenance Tracking

### Tracking Entity Provenance

```python
from semantica.kg import ProvenanceTracker

tracker = ProvenanceTracker()

# Track entity provenance
tracker.track_entity(
    "entity_1",
    source="source_1",
    metadata={"confidence": 0.9, "extraction_method": "ner"}
)

# Track relationship provenance
tracker.track_relationship(
    "rel_1",
    source="source_2",
    metadata={"confidence": 0.85}
)
```

### Retrieving Provenance

```python
from semantica.kg import ProvenanceTracker

tracker = ProvenanceTracker()

# Get all sources for an entity
sources = tracker.get_all_sources("entity_1")
for source in sources:
    print(f"Source: {source['source']}")
    print(f"Timestamp: {source['timestamp']}")
    print(f"Metadata: {source['metadata']}")

# Get complete lineage
lineage = tracker.get_lineage("entity_1")
print(f"First seen: {lineage['first_seen']}")
print(f"Last updated: {lineage['last_updated']}")
print(f"Total sources: {len(lineage['sources'])}")
```

## Using Methods

### Method Functions

```python
from semantica.kg.methods import (
    build_kg,
    analyze_graph,
    resolve_entities,
    detect_conflicts,
    calculate_centrality,
    detect_communities,
    analyze_connectivity,
    deduplicate_graph,
    query_temporal,
    # Graph algorithm functions
    compute_node_embeddings,
    calculate_similarity,
    predict_links,
    find_shortest_path,
    calculate_pagerank,
    detect_communities_label_propagation
)

# Build knowledge graph
kg = build_kg(sources, method="default")

# Analyze graph
analysis = analyze_graph(kg, method="default")

# Resolve entities
resolved = resolve_entities(entities, method="fuzzy")

# Detect conflicts
conflicts = detect_conflicts(kg, method="default")

# Calculate centrality
centrality = calculate_centrality(kg, method="degree")

# Detect communities
communities = detect_communities(kg, method="louvain")

# Analyze connectivity
connectivity = analyze_connectivity(kg, method="default")

# Deduplicate graph
deduplicated = deduplicate_graph(kg, method="default")

# Query temporal
temporal_result = query_temporal(kg, method="time_point", at_time="2024-01-01")

# Graph algorithm functions
embeddings = compute_node_embeddings(graph_store, node_labels=["Entity"], relationship_types=["RELATED_TO"])
similarity = calculate_similarity(graph_store, "node1", "node2", method="cosine")
predicted_links = predict_links(graph_store, top_k=20, method="preferential_attachment")
shortest_path = find_shortest_path(graph, "source", "target", method="dijkstra")
pagerank_scores = calculate_pagerank(graph, max_iterations=100, damping_factor=0.85)
label_communities = detect_communities_label_propagation(graph, max_iterations=50)
```

### Graph Algorithm Convenience Functions

```python
from semantica.kg.methods import (
    compute_node_embeddings,
    calculate_similarity,
    predict_links,
    find_shortest_path,
    calculate_pagerank,
    detect_communities_label_propagation
)

# Node embeddings with Node2Vec
embeddings = compute_node_embeddings(
    graph_store,
    node_labels=["Entity", "Person"],
    relationship_types=["RELATED_TO", "KNOWS"],
    embedding_dimension=128,
    walk_length=80,
    num_walks=10
)

print(f"Generated embeddings for {len(embeddings)} nodes")

# Similarity calculation between nodes
similarity = calculate_similarity(
    graph_store,
    "node_1",
    "node_2",
    method="cosine"
)
print(f"Cosine similarity: {similarity:.4f}")

# Link prediction
predicted_links = predict_links(
    graph_store,
    top_k=10,
    method="preferential_attachment"
)
print(f"Predicted {len(predicted_links)} potential links")

# Path finding
path = find_shortest_path(
    graph,
    "source_node",
    "target_node",
    method="dijkstra"
)
print(f"Shortest path: {' -> '.join(path)}")

# PageRank centrality
pagerank_scores = calculate_pagerank(
    graph,
    max_iterations=100,
    damping_factor=0.85
)
print(f"PageRank calculated for {len(pagerank_scores)} nodes")

# Label Propagation community detection
communities = detect_communities_label_propagation(
    graph,
    max_iterations=50
)
print(f"Detected {len(communities['communities'])} communities")
```

### Getting Methods

```python
from semantica.kg.methods import get_kg_method

# Get a specific method
build_method = get_kg_method("build", "default")
if build_method:
    kg = build_method(sources)

# Get graph algorithm method
embedding_method = get_kg_method("embeddings", "node2vec")
if embedding_method:
    embeddings = embedding_method(graph_store, ["Entity"], ["RELATED_TO"])
```

### Listing Available Methods

```python
from semantica.kg.methods import list_available_methods

# List all available methods
all_methods = list_available_methods()
print("Available methods:")
for task, methods in all_methods.items():
    print(f"  {task}: {methods}")

# List methods for a specific task
build_methods = list_available_methods("build")
print(f"Build methods: {build_methods}")

# List graph algorithm methods
algorithm_methods = list_available_methods("embeddings")
print(f"Embedding methods: {algorithm_methods}")
```

## Using Registry

### Method Registry

```python
from semantica.kg.registry import method_registry

def custom_build_method(sources, **kwargs):
    """Custom build method."""
    # Your custom implementation
    return {"entities": [], "relationships": [], "metadata": {}}

# Register custom method
method_registry.register("build", "custom_build", custom_build_method)

# Use custom method
from semantica.kg.methods import build_kg
kg = build_kg(sources, method="custom_build")
```

### Algorithm Registry

```python
from semantica.kg.registry import algorithm_registry

# Register custom algorithm
class CustomEmbedder:
    def __init__(self, dimension=64):
        self.dimension = dimension
    
    def compute(self, graph_store, node_labels, relationship_types):
        return {"node1": [0.1] * 64, "node2": [0.2] * 64}

algorithm_registry.register(
    "embeddings",
    "custom_algo",
    CustomEmbedder,
    metadata={
        "description": "Custom embedding algorithm",
        "parameters": ["dimension"],
        "complexity": "O(V * E)",
        "quality": "Custom"
    },
    capabilities=["custom_feature1", "custom_feature2"]
)

# Use custom algorithm
from semantica.kg.methods import compute_node_embeddings
embeddings = compute_node_embeddings(graph_store, method="custom_algo")
```

### Algorithm Discovery

```python
from semantica.kg.registry import algorithm_registry

# Discover available algorithms
all_algorithms = algorithm_registry.list_all()
print("Available algorithms:")
for category, algorithms in all_algorithms.items():
    print(f"  {category}: {algorithms}")

# Get algorithm metadata
metadata = algorithm_registry.get_metadata("embeddings", "node2vec")
print("Node2Vec metadata:", metadata)

# Get algorithm capabilities
capabilities = algorithm_registry.get_capabilities("path_finding", "dijkstra")
print("Dijkstra capabilities:", capabilities)

# Create algorithm instance
embedder = algorithm_registry.create_instance("embeddings", "node2vec", embedding_dimension=256)
```

### Unregistering Methods and Algorithms

```python
from semantica.kg.registry import method_registry, algorithm_registry

# Unregister a method
method_registry.unregister("build", "custom_build")

# Unregister an algorithm
algorithm_registry.unregister("embeddings", "custom_algo")
```

### Listing Registered Items

```python
from semantica.kg.registry import method_registry, algorithm_registry

# List all registered methods
all_methods = method_registry.list_all()
print("All registered methods:", all_methods)

# List all registered algorithms
all_algorithms = algorithm_registry.list_all()
print("All registered algorithms:", all_algorithms)

# List methods for a specific task
build_methods = method_registry.list_all("build")
print("Build methods:", build_methods)

# List algorithms for a specific category
embedding_algorithms = algorithm_registry.list_category("embeddings")
print("Embedding algorithms:", embedding_algorithms)
```

## Configuration

### Environment Variables

```bash
# Set KG configuration via environment variables
export KG_MERGE_ENTITIES=true
export KG_RESOLUTION_STRATEGY=fuzzy
export KG_ENABLE_TEMPORAL=false
export KG_TEMPORAL_GRANULARITY=day
export KG_SIMILARITY_THRESHOLD=0.8
```

### Programmatic Configuration

```python
from semantica.kg.config import kg_config

# Set configuration programmatically
kg_config.set("merge_entities", True)
kg_config.set("resolution_strategy", "fuzzy")
kg_config.set("similarity_threshold", 0.8)

# Get configuration
merge_entities = kg_config.get("merge_entities", default=True)
strategy = kg_config.get("resolution_strategy", default="fuzzy")

# Set method-specific configuration
kg_config.set_method_config("build", merge_entities=True, resolve_conflicts=True)

# Get method-specific configuration
build_config = kg_config.get_method_config("build")
```

### Config Files

```yaml
# config.yaml
kg:
  merge_entities: true
  resolution_strategy: fuzzy
  enable_temporal: false
  temporal_granularity: day
  similarity_threshold: 0.8

kg_methods:
  build:
    merge_entities: true
    resolve_conflicts: true
  resolve:
    similarity_threshold: 0.8
```

```python
from semantica.kg.config import KGConfig

# Load from config file
kg_config = KGConfig(config_file="config.yaml")
```

## Advanced Examples

### Complete Knowledge Graph Pipeline with Graph Algorithms

```python
from semantica.kg import (
    GraphBuilder,
    EntityResolver,
    GraphAnalyzer,
    CentralityCalculator,
    CommunityDetector,
    NodeEmbedder,
    SimilarityCalculator,
    PathFinder,
    LinkPredictor
)

# 1. Build knowledge graph
builder = GraphBuilder(merge_entities=True)
kg = builder.build(sources)

# 2. Resolve entities
resolver = EntityResolver(strategy="fuzzy", similarity_threshold=0.8)
entities = kg["entities"]
resolved_entities = resolver.resolve_entities(entities)
kg["entities"] = resolved_entities

# 3. Validate graph
# Validation logic temporarily removed

# 4. Analyze graph
analyzer = GraphAnalyzer()
analysis = analyzer.analyze_graph(kg)
print(f"Graph density: {analysis['density']}")
print(f"Average degree: {analysis['avg_degree']}")

# 5. Calculate traditional centrality
centrality_calc = CentralityCalculator()
degree_centrality = centrality_calc.calculate_degree_centrality(kg)
print("Top 5 nodes by degree:")
for ranking in degree_centrality["rankings"][:5]:
    print(f"  {ranking['node']}: {ranking['score']}")

# 6. Calculate PageRank centrality
pagerank_scores = centrality_calc.calculate_pagerank(kg, max_iterations=100, damping_factor=0.85)
print("Top 5 nodes by PageRank:")
for node_id, score in sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {node_id}: {score:.4f}")

# 7. Detect traditional communities
community_detector = CommunityDetector()
communities_result = community_detector.detect_communities(kg, algorithm="louvain")
print(f"Found {len(communities_result['communities'])} communities")

# 8. Detect communities with Label Propagation
label_communities = community_detector.detect_communities_label_propagation(kg, max_iterations=50)
print(f"Label propagation found {len(label_communities['communities'])} communities")

# 9. Generate node embeddings
embedder = NodeEmbedder(embedding_dimension=64, walk_length=40, num_walks=5)
embeddings = embedder.compute_embeddings(graph_store, ["Entity"], ["RELATED_TO"])
print(f"Generated embeddings for {len(embeddings)} nodes")

# 10. Calculate similarities between embeddings
similarity_calc = SimilarityCalculator()
query_embedding = embeddings.get("node_123")
if query_embedding:
    similarities = similarity_calc.batch_similarity(embeddings, query_embedding, top_k=5)
    print("Most similar nodes to node_123:")
    for node_id, similarity in similarities.items():
        print(f"  {node_id}: {similarity:.4f}")

# 11. Predict potential links
link_predictor = LinkPredictor(method="preferential_attachment")
predicted_links = link_predictor.predict_links(graph_store, top_k=10)
print("Top predicted links:")
for node1, node2, score in predicted_links[:5]:
    print(f"  {node1} - {node2}: {score:.4f}")

# 12. Find shortest paths
path_finder = PathFinder()
source_node = list(graph.nodes())[0]
target_node = list(graph.nodes())[-1]

dijkstra_path = path_finder.dijkstra_shortest_path(graph, source_node, target_node)
print(f"Dijkstra path: {' -> '.join(dijkstra_path)}")

# 13. Find multiple shortest paths
all_paths = path_finder.all_shortest_paths(graph, source_node)
print(f"Paths from {source_node}: {len(all_paths)} targets reached")
```

### Graph Analytics Workflow

```python
from semantica.kg import (
    GraphAnalyzer,
    CentralityCalculator,
    CommunityDetector,
    ConnectivityAnalyzer,
    NodeEmbedder,
    SimilarityCalculator,
    PathFinder,
    LinkPredictor
)

# Comprehensive analysis
analyzer = GraphAnalyzer()
analysis = analyzer.analyze_graph(kg)

# Centrality analysis
centrality_calc = CentralityCalculator()
all_centrality = centrality_calc.calculate_all_centrality(kg)

# Community detection
community_detector = CommunityDetector()
traditional_communities = community_detector.detect_communities(kg, algorithm="louvain")
label_communities = community_detector.detect_communities_label_propagation(kg, max_iterations=50)

# Connectivity analysis
connectivity_analyzer = ConnectivityAnalyzer()
connectivity = connectivity_analyzer.analyze_connectivity(kg)
components = connectivity_analyzer.find_connected_components(kg)
bridges = connectivity_analyzer.identify_bridges(kg)

# Node embeddings
embedder = NodeEmbedder()
embeddings = embedder.compute_embeddings(graph_store, ["Entity"], ["RELATED_TO"])

# Similarity analysis
similarity_calc = SimilarityCalculator()
# Find most similar node pairs
pairwise_similarities = similarity_calc.pairwise_similarity(embeddings, method="cosine")
top_similarities = sorted(pairwise_similarities.items(), key=lambda x: x[1], reverse=True)[:10]

# Path finding analysis
path_finder = PathFinder()
# Find critical paths in the graph
critical_paths = []
for node1 in list(graph.nodes())[:10]:
    for node2 in list(graph.nodes())[:10]:
        if node1 != node2:
            path = path_finder.dijkstra_shortest_path(graph, node1, node2)
            if path:
                critical_paths.append((node1, node2, len(path)))

# Sort by path length
critical_paths.sort(key=lambda x: x[2])
print("Shortest paths:")
for node1, node2, length in critical_paths[:10]:
    print(f"  {node1} -> {node2}: {length} steps")

# Link prediction analysis
link_predictor = LinkPredictor()
# Find high-potential connections
high_potential = link_predictor.predict_links(graph_store, method="preferential_attachment", top_k=20)
common_neighbors = link_predictor.predict_links(graph_store, method="common_neighbors", top_k=20)

print("High potential links (Preferential Attachment):")
for node1, node2, score in high_potential[:5]:
    print(f"  {node1} - {node2}: {score:.4f}")

print("High potential links (Common Neighbors):")
for node1, node2, score in common_neighbors[:5]:
    print(f"  {node1} - {node2}: {score:.4f}")
```

### Real-World Application: Knowledge Graph Analytics

```python
from semantica.kg import (
    NodeEmbedder, SimilarityCalculator, PathFinder, LinkPredictor,
    CentralityCalculator, CommunityDetector
)

# Load or build your knowledge graph
# kg = load_kg() or kg = build_kg(sources)

# 1. Identify influential entities using PageRank
centrality_calc = CentralityCalculator()
pagerank_scores = centrality_calc.calculate_pagerank(kg, max_iterations=100)

influential_entities = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)[:10]
print("Top 10 most influential entities:")
for entity_id, score in influential_entities:
    print(f"  {entity_id}: {score:.4f}")

# 2. Find similar entities using embeddings
embedder = NodeEmbedder()
embeddings = embedder.compute_embeddings(kg, ["Entity"], ["RELATED_TO"])

similarity_calc = SimilarityCalculator()
target_entity = influential_entities[0][0]  # Most influential entity
target_embedding = embeddings.get(target_entity)

similar_entities = similarity_calc.batch_similarity(embeddings, target_embedding, top_k=10)
print(f"Entities similar to {target_entity}:")
for entity_id, similarity in similar_entities.items():
    print(f"  {entity_id}: {similarity:.4f}")

# 3. Discover communities with Label Propagation
community_detector = CommunityDetector()
communities = community_detector.detect_communities_label_propagation(kg, max_iterations=100)

print(f"Discovered {len(communities['communities'])} communities")
for i, community in enumerate(communities["communities"][:5]):
    print(f"Community {i}: {len(community)} entities")

# 4. Predict missing relationships
link_predictor = LinkPredictor(method="adamic_adar")
missing_links = link_predictor.predict_links(kg, top_k=20, exclude_existing=True)

print("Top predicted missing relationships:")
for node1, node2, score in missing_links[:10]:
    print(f"  {node1} - {node2}: {score:.4f}")

# 5. Find optimal paths for information flow
path_finder = PathFinder()

# Find shortest paths between top entities
top_entities = [entity_id for entity_id, _ in influential_entities[:5]]
optimal_paths = []

for i, source in enumerate(top_entities):
    for j, target in enumerate(top_entities[i+1:], top_entities):
        path = path_finder.dijkstra_shortest_path(kg, source, target)
        if path:
            optimal_paths.append((source, target, len(path)))
        else:
            optimal_paths.append((source, target, float('inf')))

print("Optimal paths between top entities:")
for source, target, length in sorted(optimal_paths, key=lambda x: x[2])[:10]:
    if length != float('inf'):
        print(f"  {source} -> {target}: {length} steps")
    else:
        print(f"  {source} -> {target}: No path found")
```

This comprehensive guide demonstrates how to use all the graph algorithms in the knowledge graph module, from basic usage to advanced real-world applications. Each algorithm is designed to work with the existing KG infrastructure and can be combined for powerful analytics workflows.

