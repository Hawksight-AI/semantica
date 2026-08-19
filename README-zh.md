# Semantica：面向上下文与可审计 AI 系统的图原生基础设施

[English](README.md) | 简体中文

Semantica 是一个开源、可自托管的图原生基础设施，用于把企业数据转化为可查询的上下文图（Context Graph）和知识图谱（KG），并在其上运行图分析、因果推理、决策追踪与合规审计。

它位于 LLM、向量数据库和 Agent 框架之下：图构建、推理和溯源不依赖 LLM。每个实体、关系、事实和决策都可以关联到来源、时间、策略和执行轨迹。

> **说明：这里的可解释性是系统级可解释性，而不是基础模型内部可解释性。** Semantica 不会暴露或重建 LLM 内部的推理过程或思维链；它解释的是模型之外的上下文、输入数据、产生的决策、来源、相关关系、应用策略和完整执行记录。

## 适用场景

- AI/ML 平台团队：为会做出重要决策的 Agent 构建结构化、可查询的上下文。
- Databricks 或 Snowflake 数据平台团队：直接从 Unity Catalog、Delta Lake 或 Snowflake 仓库构建带血缘的知识图谱。
- 合规、风险与审计团队：回答“AI 为什么做出这个决定”，并导出审计材料。
- 金融、医疗、法律、政府、国防等不能接受黑盒和数据外发的组织。
- 希望自托管、可替换后端、避免供应商锁定的平台与基础设施工程师。
- 需要从多源、脏数据中抽取实体和关系，并检测冲突、合并重复实体的数据与知识工程师。

## 核心能力

- **上下文图**：把实体、关系、事实、决策和证据组织成可遍历的图。
- **决策智能**：决策是一等图节点，可查询先例、因果链和下游影响。
- **治理与本体**：SHACL 约束、冲突检测、合规规则、OWL 生成、SKOS 词表和可视化编辑器。
- **完整审计**：每个事实都可以记录 W3C PROV-O 溯源，并导出 JSON、CSV 或 RDF。
- **确定性推理**：支持前向链、Rete、Datalog 和 SPARQL，并返回可解释路径。
- **知识管线**：多源摄取、实体感知切分、NER/关系/事件抽取、图构建、语义去重和保留来源的合并。
- **企业数据连接器**：Databricks（Unity Catalog、Delta Lake、PAT/OAuth M2M、目录/表/血缘）和 Snowflake（仓库/数据库/模式、密码/密钥对/OAuth）。
- **图分析与存储**：中心性、社区发现、链接预测、最短路径；同时支持 RDF 三元组库、LPG 图数据库和向量存储。
- **可视化与集成**：浏览器工作台、REST API、MCP Server、CLI、Agno/CrewAI，以及多个编辑器插件。

## 与传统 RAG 的区别

| 能力 | 向量数据库 + RAG | 纯 LLM Memory | **Semantica** |
| --- | --- | --- | --- |
| 召回方式 | 向量相似度 | Token 窗口 | 图遍历 + 语义搜索 |
| 决策历史 | 不保存 | 不保存 | 一等可查询对象 |
| 来源溯源 | 无 | 无 | W3C PROV-O、关联原始来源 |
| 推理 | 无 | 黑盒 | 前向链、Rete、Datalog、SPARQL |
| 冲突检测 | 静默覆盖 | 静默覆盖 | 检测、标记并按策略解决 |
| 时间回溯 | 不支持 | 不支持 | 任意时间点的图快照 |
| 合规导出 | 无 | 无 | PROV-O、SHACL、OWL、RDF |
| 实体消歧 | 不支持 | 不支持 | Blocking + 语义去重 |
| 多 Agent 上下文 | 每个 Agent 独立 | 每个 Agent 独立 | 共享的智能上下文层 |

Semantica 是对现有技术栈的补充，不要求替换 LLM、向量存储或 Agent 框架。

## 快速开始

```bash
pip install semantica
```

```python
from semantica.context import ContextGraph

graph = ContextGraph(advanced_analytics=True)

# 每个 Agent 决策都成为可查询、可审计的图节点
decision_id = graph.record_decision(
    category="vendor_selection",
    scenario="为 HIPAA 工作负载选择云服务商",
    reasoning="AWS 提供 BAA、成熟的 HIPAA 工具和现有团队经验",
    outcome="selected_aws",
    confidence=0.93,
)

# 查询因果链、相似先例、影响范围和策略结果
chain = graph.trace_decision_chain(decision_id)
similar = graph.find_similar_decisions("cloud vendor", max_results=5)
impact = graph.analyze_decision_impact(decision_id)
compliant = graph.check_decision_rules({"category": "vendor_selection"})
```

安装后可用以下命令进行快速自检：

```bash
semantica doctor
# Python 3.11.9         pass
# semantica 0.6.5       pass
# faiss vector store    pass
# Config file           pass    ~/.semantica/config.yaml
```

## 架构

Semantica 是一条端到端、每个阶段均可独立导入的管线：

```text
Sources → Ingest → Parse → Normalize → Split → Extract → Conflict Detection → Deduplication
   → Knowledge Graph → [ Ontology · Reasoning · Provenance · Decisions ] → Enriched KG
   → Vector Store + Polyglot Graph Store (RDF & LPG) → Export / Visualize / REST · MCP · CLI
```

- **Ingest**：文件、网页、数据库、Databricks、Snowflake、云服务、消息流、Git、邮件和 MCP。
- **Parse / Normalize / Split**：文档解析、文本/实体/日期规范化，以及 GraphRAG 实体感知切分。
- **Extract / Conflict / Deduplicate**：NER、关系、事件和三元组抽取，冲突事实在合并前被标记。
- **Knowledge Graph**：`GraphBuilder` 构建图，支持双时间事实和图分析。
- **Ontology / Reasoning / Provenance / Decisions**：SHACL/OWL 治理、Rete/Datalog/SPARQL 推理、PROV-O 血缘和一等决策记录。
- **Storage**：Oxigraph、Blazegraph、Apache Jena、Eclipse RDF4J、Neo4j、FalkorDB、Apache AGE、AWS Neptune，以及 FAISS、Qdrant、Weaviate、Milvus、Pinecone、PgVector。
- **Outputs**：RDF、OWL、Parquet、Cypher、JSON-LD，交互式可视化、REST、MCP 和 CLI。

完整管线图和决策智能生命周期见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 决策智能

决策不是日志行，而是带完整生命周期的图节点。常用 API 包括：

```text
record_decision()          → 保存带结构化上下文的决策节点
add_causal_relationship()  → 连接上游原因与下游影响
find_similar_decisions()   → 搜索历史语义先例
trace_decision_chain()     → 回溯完整因果祖先
analyze_decision_impact()  → 查看该决策影响的下游对象
check_decision_rules()     → 对照可配置规则进行策略检查
export / audit trail       → 导出 W3C PROV-O、CSV 或 JSON
```

因果关系类型必须是 `CAUSED`、`INFLUENCED` 或 `PRECEDENT_FOR`。决策和事实可以关联到来源文件、提取器、时间和元数据，方便审计和监管提交。

## 上下文图

上下文图回答的不只是“什么相似”，还包括“什么与它相连、为什么相连、如何相连”：

```python
from semantica.context import ContextGraph, AgentContext
from semantica.vector_store import VectorStore

graph = ContextGraph(advanced_analytics=True)
graph.add_node("acme_corp", "Organization", name="Acme Corp", industry="SaaS")
graph.add_node("alice_chen", "Person", name="Alice Chen", role="CTO")
graph.add_edge("alice_chen", "acme_corp", edge_type="works_for", since="2019-03-01")

neighbors = graph.get_neighbors("acme_corp", hops=2)
snapshot = graph.state_at("2024-01-01")

ctx = AgentContext(
    vector_store=VectorStore(backend="faiss"),
    knowledge_graph=graph,
)
ctx.store("Alice 在 2024 年第一季度批准了 Acme 的续约", conversation_id="conv_001")
retrieved = ctx.retrieve("谁批准了 Acme 合同？")
```

图遍历能够找到向量相似度容易遗漏的多跳关系；每个节点都可带来源和时间，冲突会在污染知识库前被标记，时间快照可以重放历史状态。

## 审计轨迹示例

```python
from semantica.context import ContextGraph
from semantica.provenance import ProvenanceManager
from semantica.export import RDFExporter

graph = ContextGraph(advanced_analytics=True)
prov = ProvenanceManager(storage_path="./audit.db")

d1 = graph.record_decision(
    category="drug_interaction_check",
    scenario="患者 P-4821 同时使用华法林和胺碘酮",
    reasoning="胺碘酮会增强华法林的抗凝作用",
    outcome="flag_for_review",
    confidence=0.91,
)
d2 = graph.record_decision(
    category="dosage_adjustment",
    scenario="P-4821 的 INR 监测计划",
    reasoning="按相互作用严重程度降低剂量，并在 5 天后复查 INR",
    outcome="dose_reduced_30pct",
    confidence=0.87,
)
graph.add_causal_relationship(d1, d2, relationship_type="CAUSED")
prov.track_entity("patient_P4821", source="ehr/medication_orders_2024.json")

RDFExporter().export(graph.to_kg_dict(), "audit_trail.ttl", format="turtle")
```

## 模块参考

每个模块都可以独立导入，并在当前源码树中提供可运行示例：

| 模块 | 用途 |
| --- | --- |
| `semantica.ingest` | 文件、网页、数据库、API、流、邮件、Git、Parquet、Databricks、Snowflake、MCP |
| `semantica.semantic_extract` | NER、关系、事件和三元组抽取 |
| `semantica.kg` | 图构建、中心性、社区发现、链接预测 |
| `semantica.reasoning` | 前向链、Rete、Datalog、SPARQL、可解释推理 |
| `semantica.vector_store` | FAISS、Qdrant、Weaviate、Milvus、Pinecone、PgVector、混合搜索 |
| `semantica.split` | 实体感知、关系感知、本体感知的 GraphRAG 切分 |
| `semantica.provenance` | W3C PROV-O 事实血缘 |
| `semantica.ontology` | OWL 生成、SHACL 验证、SKOS 词表 |
| `semantica.conflicts` | 多源事实冲突检测与解决 |
| `semantica.deduplication` | 大规模实体消歧与合并 |
| `semantica.normalize` | 文本、实体、日期、数字规范化与数据清洗 |
| `semantica.pipeline` | 声明式并行管线 DSL |
| `semantica.export` | RDF、OWL、Parquet、Cypher、JSON-LD |
| `semantica.visualization` | 图、社区、本体层级和时间线可视化 |

## 常见配方

### 端到端 GraphRAG

1. 使用 `FileIngestor` 摄取文档。
2. 使用 `TextSplitter(method="entity_aware")` 切分，避免实体跨块断开。
3. 使用 `NamedEntityRecognizer` 和 `RelationExtractor` 抽取结构化信息。
4. 用 `GraphBuilder(merge_entities=True, enable_temporal=True)` 构建图。
5. 使用 `HybridSearch` 结合向量与图上下文检索。

### AML 规则引擎

使用 `ReteEngine`、`Rule` 和 `Fact` 构建制裁国家、大额交易等规则，对批量交易执行模式匹配，并输出合规复核标记。

### 本体到知识图谱

使用 `OntologyGenerator` 从抽取结果生成本体，用 `OntologyValidator` 执行验证，最后通过 `RDFExporter` 导出 Turtle 等格式。

## 功能概览

- **时间智能**：时间点快照、Allen 区间代数（13 种关系）、双时间溯源。
- **距离智能**：N×N 语义距离矩阵、ego 可视化、距离分段和嵌入缓存。
- **语义抽取**：NER、关系、事件、三元组和共指消解。
- **推理引擎**：前向链、Rete、演绎、溯因、SPARQL、Datalog。
- **冲突检测**：值、类型、关系、时间和逻辑冲突，多种解决策略。
- **本体中心**：SHACL Studio、可视化编辑器、本体对齐和健康看板。
- **企业平台**：Databricks 与 Snowflake 原生摄取、目录/表/模式信息和数据血缘查看。
- **LLM 提供商**：OpenAI、Anthropic、Gemini、Mistral、Llama、Groq、Cohere、Azure OpenAI、Bedrock、Ollama、DeepSeek、Perplexity、Together AI、Fireworks AI、Replicate、HuggingFace 等，可通过 `semantica.llms` 和 LiteLLM 使用。

## 性能

以下数据来自 v0.5.0、118,000 节点生产图（AMD EPYC、64 GB RAM）：

| 操作 | 之前 | 之后 | 改善 |
| --- | ---: | ---: | ---: |
| 节点搜索（118k 节点） | 24 ms | 0.004 ms | **约 6,000 倍** |
| 嵌入缓存命中 | 冷加载 | 基于 revision 的缓存 | **吞吐量约 10 倍** |
| 语义去重 | 基线 | 优化候选生成 | **约 6.98 倍** |
| 候选生成 | 基线 | Blocking 策略 | **快 63.6%** |

结果取决于硬件、数据拓扑和后端选择。可运行 `pytest tests/vector_store/test_performance_benchmarks.py -s` 测量自己的数据。

## CLI

CLI 随包发布，无需单独安装：

```bash
pip install semantica
semantica        # 启动工作台
semantica doctor # 健康检查
semantica --help # 分组命令参考
```

命令组包括：`ingest`、`parse`、`extract`、`kg`、`reason`、`decision`、`temporal`、`provenance`、`ontology`、`embed`、`deduplicate`、`validate`、`export`、`visualize`、`pipeline`、`server`、`explorer`、`mcp`、`doctor`、`shell`、`init`、`watch`。

完整 CLI 参考见 [docs.getsemantica.ai](https://docs.getsemantica.ai/)。

## 集成

Semantica 提供 Claude Code、Cursor、Codex、Windsurf、Cline、Continue、VS Code 和 OpenClaw 插件；为所有 MCP 客户端提供 MCP Server；同时提供 REST API，以及 Agno 和 CrewAI 的一等集成。

### MCP Server

```bash
python -m semantica.mcp_server
# 或
semantica-mcp
```

客户端配置示例：

```json
{
  "mcpServers": {
    "semantica": {
      "command": "python",
      "args": ["-m", "semantica.mcp_server"]
    }
  }
}
```

MCP 工具包括 `extract_entities`、`extract_relations`、`record_decision`、`query_decisions`、`find_precedents`、`get_causal_chain`、`add_entity`、`add_relationship`、`run_reasoning`、`get_graph_analytics`、`export_graph` 和 `get_graph_summary`。

### REST API

```bash
# 以下示例使用 Bash/Zsh；PowerShell 请改用：
# $env:SEMANTICA_API_KEY = "replace-with-a-strong-random-value"
export SEMANTICA_API_KEY="replace-with-a-strong-random-value"
python -m semantica.server   # 默认端口 8000

curl -X POST http://localhost:8000/api/enrich/extract \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SEMANTICA_API_KEY" \
  -d '{"text": "Apple CEO Tim Cook announced record earnings."}'

curl -H "X-API-Key: $SEMANTICA_API_KEY" \
  "http://localhost:8000/api/decisions?category=vendor_selection"
curl -H "X-API-Key: $SEMANTICA_API_KEY" \
  "http://localhost:8000/api/graph/node/acme_corp/neighbors?depth=2"
```

`SEMANTICA_API_KEY` 未设置时，除 `/api/health` 和 `/api/info` 外的受保护路由会以 `503` 失败关闭；密钥错误或缺失会返回 `401`。REST 覆盖 `enrich`、`graph`、`decisions`、`reasoning`、`provenance`、`ontology`、`embeddings`、`search`、`export`、`pipeline`、`temporal` 和 `deduplication`。

## Knowledge Explorer

Knowledge Explorer 是基于 React 19 和 Sigma.js 的浏览器图工作台，可用于平移缩放图、回放时间线、查看决策因果链、合并重复实体、编辑本体和检查 PROV-O 血缘。

无需 Node.js 即可启动。下面是**仅限本机开发**的最快方式：默认绑定 `127.0.0.1`，并显式允许匿名访问。不要将此模式与 `--host 0.0.0.0` 或任何可被其他设备访问的地址一起使用。

```bash
pip install "semantica[explorer]"
# Bash/Zsh
SEMANTICA_ALLOW_ANONYMOUS=true semantica-explorer --graph my_graph.json
# 控制台地址：http://127.0.0.1:8000
```

PowerShell 用户可以运行 `$env:SEMANTICA_ALLOW_ANONYMOUS = "true"`，再执行 `semantica-explorer --graph my_graph.json`。

用于网络可达或生产环境时，设置 `SEMANTICA_API_KEY`，并让每个 API 客户端通过 `X-API-Key` 发送该值。当前内置 Explorer 浏览器前端不会为其 API 请求提供密钥输入；如需安全地发布该前端，请使用受信任的反向代理完成用户认证，并仅在代理已验证用户后向后端注入匹配的 `X-API-Key` 请求头。确保后端端口不直接暴露。

开发者本地设置见 [explorer/README.md](explorer/README.md)。

## v0.6.5 安全更新

这是一个安全版本，建议升级。主要修复包括：

- Explorer API 全部路由增加 `SEMANTICA_API_KEY` 认证，未配置时默认失败关闭。
- 修复本体 URL 跳转绕过校验导致的 SSRF。
- 修复 Neptune、Neo4j、FalkorDB 中未校验标签、关系类型和属性键导致的 Cypher 注入。
- 修复 Blazegraph、RDF4J、Jena 中未校验 IRI 导致的 SPARQL 注入。
- 修复 WebSocket 握手缺少 Origin 校验的问题。
- 修复 SPARQL 查询校验中的多项式 ReDoS。
- 新增内置 Oxigraph、完善 PROV-O 信任/规范支持，并加入 Altair Anzo 三元组存储后端。

详见 [RELEASE_NOTES.md](RELEASE_NOTES.md) 和 [CHANGELOG.md](CHANGELOG.md)。

## 面向高风险领域

Semantica 适用于需要解释、审计和责任追踪的环境：金融信贷与反洗钱、医疗临床决策与药物相互作用、法律证据和合同分析、政府与国防政策治理、执法案件关联、网络安全事件响应，以及需要安全验证的自动化系统。

## 安装与可选组件

```bash
pip install semantica           # 核心
pip install semantica[all]      # 全部功能
pip install semantica[agno]                 # Agno 多 Agent
pip install semantica[crewai]               # CrewAI
pip install semantica[llm-litellm]          # LiteLLM 与多家 LLM
pip install semantica[graph-neo4j]          # Neo4j
pip install semantica[graph-falkordb]       # FalkorDB
pip install semantica[graph-apache-age]     # Apache AGE
pip install semantica[graph-amazon-neptune] # AWS Neptune
pip install semantica[tripletstore-oxigraph] # 内置 RDF 存储
pip install semantica[vectorstore-qdrant]   # Qdrant
pip install semantica[vectorstore-pinecone] # Pinecone
pip install semantica[db-snowflake]         # Snowflake
pip install semantica[db-databricks]       # Databricks
pip install semantica[ingest-parquet]       # Parquet / PyArrow
pip install semantica[ingest-arrow]         # Apache Arrow
pip install semantica[viz]                  # HTML 交互式可视化
pip install semantica[watch]                # 目录文件监视
pip install semantica[explorer]             # Knowledge Explorer
```

生产部署建议使用 Docker 或 Kubernetes，并设置 `SEMANTICA_API_KEY`，配置持久化 LPG/RDF 存储和托管向量后端。受保护 API 客户端必须以 `X-API-Key` 请求头发送同一个值。源码开发：

```bash
git clone https://github.com/semantica-agi/semantica.git
cd semantica
pip install -e ".[dev]"
pytest tests/
```

## 企业服务与社区

- 企业服务：本地部署、私有云、定制领域实现、SLA 支持和合规行业专业服务，见 [getsemantica.ai](https://getsemantica.ai/)。
- 文档：[docs.getsemantica.ai](https://docs.getsemantica.ai/)
- Discord：[discord.gg/sV34vps5hH](https://discord.gg/sV34vps5hH)
- GitHub Discussions：[问答与功能请求](https://github.com/semantica-agi/semantica/discussions)
- GitHub Issues：[问题反馈](https://github.com/semantica-agi/semantica/issues)
- Cookbook：[可运行的 Jupyter Notebook](https://github.com/semantica-agi/semantica/tree/main/cookbook)
- 变更记录：[CHANGELOG.md](CHANGELOG.md) · [RELEASE_NOTES.md](RELEASE_NOTES.md)

## 贡献

欢迎提交修复、功能、测试和文档：

1. Fork 仓库并创建分支。
2. 执行 `pip install -e ".[dev]"`。
3. 为改动补充测试，运行 `pytest tests/`。
4. 提交 Pull Request，并按照 [CONTRIBUTING.md](CONTRIBUTING.md) 的完整指南操作。

## 许可证

MIT License。项目主页：[semantica-agi/semantica](https://github.com/semantica-agi/semantica)
