# Shiliu V3 — Stage 2 Implementation and Evidence Report

结论分类：`Stage 2 Delivered; Ready for Version Session Re-review`

本报告包含 Stage 2 初次实现和 Closure Fix 的最终证据。Closure Fix 只修改 Dense Projection、Dense reuse metadata semantics、RRF tie-break、测试、状态和本报告。未修改 Evidence Chunking、Stage 1 FTS、Product Pipeline、Taxonomy 或 Web；未进入 Stage 3。

## 1. Closure Scope and Integrity

[Confirmed Fact]

```text
Project: /Users/elliot/new-systems/agent-job-prep/Shiliu
Branch: codex/v3-domain-completion
HEAD: 4673a8f
Architecture: arm64
Project Python: 3.12.13
```

保留且未重构：EmbeddingProvider boundary、FastEmbed provider、当前 BGE 模型、SQLite float32 BLOB、NumPy exact normalized dot product、Dense rebuild/reuse/replace/delete、Stage 1 filters、RRF 基础结构、CLI modes 和 lazy loading。

本轮没有修改 [chunking.py](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/chunking.py)。结束核验：

```text
retrieval_units=1547
retrieval_units_fts=1547
retrieval_dense_vectors=1547
Video vectors=142
Transcript Chunk vectors=1405
duplicate Dense unit IDs=0
damaged vectors=0
PRAGMA integrity_check=ok
PRAGMA foreign_key_check=[]
```

## 2. Same-model Tokenizer Resolution

[Confirmed Fact]

没有新增依赖。FastEmbed 当前实际运行对象 `OnnxTextEmbedding.tokenizer` 是已安装 `tokenizers.Tokenizer`，来自同一模型快照：

```text
model=BAAI/bge-small-zh-v1.5
tokenizer type=tokenizers.Tokenizer
truncation direction=Right
truncation max_length=512
post processor=[CLS] sequence [SEP]
```

实现位置：

- [EmbeddingProvider token boundary](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/dense.py:49)
- [FastEmbed count_tokens/truncate_text](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/dense.py:83)

本地 tokenizer 实测：

```text
MCP -> [CLS] [UNK] [SEP]
模型调用外部工具时使用的标准协议 -> 18 tokens including CLS/SEP
```

因此 Projection 不再用字符数假装 token budget，也不依赖模型内部静默截断。

## 3. Token-budget-aware Video Projection V2

[Confirmed Fact]

实现：[project_embedding_text](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/dense.py:134)

```text
old projection version=v3-dense-projection-v1
new projection version=v3-dense-projection-v2
hard model maximum=512 tokens
application text budget=480 tokens
reserved budget=32 tokens
```

固定顺序、短标签和 content-token 配额：

| Priority | Source field | Label | Content-token quota |
|---:|---|---|---:|
| 1 | Title | T | 64 |
| 2 | Summary Conclusion | C | 72 |
| 3 | Summary Key Points | K | 96 |
| 4 | Summary Entities / Models / Tools / Projects | E | 56 |
| 5 | Uploader | U | 20 |
| 6 | User Notes | N | 32 |
| 7 | Active Favorite Folder Titles | F | 20 |
| 8 | Description | D | 40 |
| 9 | Summary Detailed Notes excerpt | S | 32 |
| 10 | Cleaned Transcript excerpt | X | 24 |

全部 content quotas 合计 456；十个单-token 标签与 `[CLS]/[SEP]` 后仍低于 480。缺失字段跳过；段落确定性去重；相同输入输出相同。Title 排第一并在存在时保留。Description、Detailed Notes 和 Cleaned Transcript 均有独立硬配额，不能挤掉高优先级字段或彼此无界吞噬预算。

正式 142 个 Video 使用真实同模型 tokenizer 的分布：

| Count | Min | Median | P95 | Max | Over 480 |
|---:|---:|---:|---:|---:|---:|
| 142 | 23 | 320 | 363 | 386 | 0 |

最大三个非正文示例：

```text
video:bilibili:BV1z6SXBzEYh:p1 tokens=386 characters=545
video:bilibili:BV1fRSfBWE5X:p1 tokens=377 characters=550
video:bilibili:BV16GjU6jEdP:p1 tokens=377 characters=707
```

`embedding_text_hash` 现在是最终 Projection 文本的 SHA-256。测试证明：

- 只改变 quota 外的低优先级尾部：Projection/hash 不变，向量复用，只刷新 `source_content_hash`；
- 改变实际进入 Projection 的 Title：Projection/hash 改变，仅对应 Unit 重新 Embed；
- Projection version mismatch 触发重建；第二次相同输入完整复用。

实现：[Dense rebuild metadata-only reuse](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/dense.py:209)。

## 4. Frozen Timestamp Evidence Boundary

[Confirmed Fact]

正式库检查：

```text
Transcript Chunk count=1405
projection_text_unchanged=true
all_have_chunk_id=true
all_have_start/end=true
subtitle sources=[ai, asr, human]
```

以下 Stage 1 定义未改变：

```text
target characters=800
normal maximum characters=1200
maximum duration=120 seconds
overlap=one complete trailing segment
chunk_id/start_time/end_time/raw-subtitle provenance=unchanged
```

版本决定：Long-context Embedding does not imply longer Evidence Chunks。Video vector 表达全局主题和高价值 metadata；Transcript Chunk vector 保留短的、带原始字幕时间窗的证据单位。

[Deferred]

Longer chunks、whole-video transcript replacement、parent-child retrieval、segment vectors、multi-vector Video、child-window reranking 和 timestamp refinement 均未实现。

## 5. RRF Approved Tie-break

[Confirmed Fact]

实现：[HybridRetrievalService](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/hybrid.py:16) 和 [_hybrid_sort_key](/Users/elliot/new-systems/agent-job-prep/Shiliu/src/shiliu/retrieval/hybrid.py:59)。

最终顺序：

```text
1. rrf_score descending
2. best_component_rank ascending
3. unit_id ascending

best_component_rank=min(available lexical_rank, available dense_rank)
```

保持不变：

```text
rrf_k=60
candidate_k=max(50, top_k*5)
fusion_version=v3-stage2-rrf-v1
```

手算 tie 案例：rank pairs `(3,45)` 与 `(10,30)` 的 RRF 都是 `8/315`；best component ranks 分别为 3 和 10，测试确认 `(3,45)` 先返回。

## 6. Model, Dependency and Storage Evidence

[Confirmed Fact]

```text
fastembed=0.8.0
onnxruntime=1.27.0
numpy=2.5.1
tokenizers=0.23.1 (already installed by fastembed; no Closure dependency change)
model id=BAAI/bge-small-zh-v1.5
embedding dimension=512
model license=mit
```

License 来自本地 `DenseModelDescription.license`，不是常识推测。本地模型：

```text
cache root=/var/folders/97/r461glzx7095wz145rtr5lmw0000gn/T/fastembed_cache
snapshot=/private/var/folders/97/r461glzx7095wz145rtr5lmw0000gn/T/fastembed_cache/models--Qdrant--bge-small-zh-v1.5/snapshots/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59
actual cache size=91 MiB
catalog declared size=0.09 GiB
```

同一新进程、已缓存模型的本地计时：

```text
first model load=0.254131 s
one document embedding smoke=0.005254 s
one query embedding smoke=0.000961 s
single Dense query (warm)=0.016943 s
single Hybrid query (warm)=0.023146 s
```

数据库存储：

```text
formal DB before initial Dense=36,483,072 bytes
formal DB after Dense=42,094,592 bytes
Dense delta=5,611,520 bytes
formal DB before Projection V2 rebuild=42,094,592 bytes
formal DB after Projection V2 rebuild=42,094,592 bytes
```

## 7. Model Suitability Probe

[Confirmed Fact]

所有 query vectors 均为 512-d float32、norm 1.0。

### 7.1 Pure ASCII

`MCP`、`LangGraph`、`RAG`、`FAISS` 两两结果完全相同：

| Pair | Cosine | Max abs difference | Exactly identical |
|---|---:|---:|---|
| MCP / LangGraph | 1.0000001192 | 0.0 | true |
| MCP / RAG | 1.0000001192 | 0.0 | true |
| MCP / FAISS | 1.0000001192 | 0.0 | true |
| LangGraph / RAG | 1.0000001192 | 0.0 | true |
| LangGraph / FAISS | 1.0000001192 | 0.0 | true |
| RAG / FAISS | 1.0000001192 | 0.0 | true |

四个 query 因相同向量共享 Dense top 3：

1. `transcript_chunk:...BV1SrLG6oEax...634ab5...` — Coding Agent / macOS CLI 工具；混合英文工具名字幕片段。
2. `transcript_chunk:...BV14pXZBMEh9...66e6a4...` — Claude 与 GLM 对比；AI 协作字幕片段。
3. `transcript_chunk:...BV1hr6EBBEhM...2a4f02...` — MemoryOS 代码精读；F1/代码实现字幕片段。

### 7.2 Mixed Chinese-English

| Pair | Cosine | Max abs difference | Identical |
|---|---:|---:|---|
| MCP 协议 / LangGraph 工作流 | 0.530986 | 0.131778 | false |
| MCP 协议 / RAG 检索增强生成 | 0.442214 | 0.143430 | false |
| MCP 协议 / FAISS 向量索引 | 0.505259 | 0.139391 | false |
| LangGraph 工作流 / RAG 检索增强生成 | 0.407108 | 0.192457 | false |
| LangGraph 工作流 / FAISS 向量索引 | 0.455155 | 0.209008 | false |
| RAG 检索增强生成 / FAISS 向量索引 | 0.519089 | 0.131256 | false |

Dense top 3：

- `MCP 协议`：MCP/Function Calling Video；同 Video 的协议定义 Chunk；同 Video 的 Streamable HTTP Chunk。
- `LangGraph 工作流`：OpenSpec workflow Video；AI 转型工作流 Chunk；AI 科研工作流 Chunk。
- `RAG 检索增强生成`：RAG 机制定义 Chunk；Skill-MAS Video；OpenClaw 混合检索 Chunk。
- `FAISS 向量索引`：RAG 源码向量索引 Chunk；工业 RAG 向量检索 Chunk；RAG 分片/索引 Chunk。

### 7.3 Chinese Semantic Descriptions

| Pair | Cosine | Max abs difference | Identical |
|---|---:|---:|---|
| 外部工具标准协议 / 状态图 Agent 工作流 | 0.466252 | 0.135085 | false |
| 外部工具标准协议 / 检索资料增强回答 | 0.578468 | 0.128510 | false |
| 外部工具标准协议 / 高维向量索引库 | 0.412306 | 0.192776 | false |
| 状态图 Agent 工作流 / 检索资料增强回答 | 0.428523 | 0.166045 | false |
| 状态图 Agent 工作流 / 高维向量索引库 | 0.361873 | 0.146465 | false |
| 检索资料增强回答 / 高维向量索引库 | 0.445958 | 0.141635 | false |

Dense top 3：

- `模型调用外部工具时使用的标准协议`：Function Call 工具调用 Chunk；MCP 本地调用 Chunk；标准化远程工具访问 Chunk。
- `用状态图组织 Agent 工作流`：AI 科研 workflow Chunk；OpenSpec workflow Video；AI 转型/知识检索 Chunk。
- `通过检索外部资料增强模型回答`：模型判断工具/RAG Chunk；AI 技术文档/提示工程 Chunk；Agent 经验检索 Chunk。
- `用于高维向量相似度搜索的索引库`：RAG 源码向量索引 Chunk；RAG embedding/向量库 Chunk；RAG 分片索引 Chunk。

[Confirmed Fact]

Decision Rule A 成立：坍缩仅发生于这些 pure-ASCII entity queries；Mixed 和中文语义向量可区分。

[Observation]

Pure ASCII technical entities are primarily served by Lexical Retrieval. Dense is intended primarily for Chinese or mixed natural-language semantic retrieval. Hybrid combines both signals but remains non-default before formal Eval。未添加 rewrite、translation 或第二模型。

## 8. Exact Entity Comparison — `MCP`

[Confirmed Fact]

Pure ASCII Dense 弱点如实保留。

### Lexical top 3

| Rank | Unit | Type | Title | Score | Method |
|---:|---|---|---|---:|---|
| 1 | `...BV1G29EBGE8b...6c982f...` | Chunk | 为什么巨头都在做 CLI？比 MCP 有哪些优势？ | 6.137341 | lexical |
| 2 | `...BV1G29EBGE8b...b054f1...` | Chunk | 同上 | 5.988809 | lexical |
| 3 | `video:bilibili:BV1G29EBGE8b:p1` | Video | 同上 | 5.908486 | lexical |

### Dense top 3

| Rank | Unit | Type | Title | Score | Method |
|---:|---|---|---|---:|---|
| 1 | `...BV1SrLG6oEax...634ab5...` | Chunk | Coding Agent / macOS CLI 工具 | 0.548667 | dense |
| 2 | `video:bilibili:BV1rQ9JBoECh:p1` | Video | Meta-Harness | 0.542068 | dense |
| 3 | `...BV14pXZBMEh9...66e6a4...` | Chunk | Claude 与 GLM 对比 | 0.539608 | dense |

### Hybrid top 3

| Rank | Unit | Title | Lex rank/score | Dense rank/score | RRF | Method |
|---:|---|---|---|---|---:|---|
| 1 | `...BV1hr6EBBEhM...2a4f02...` | MemoryOS 代码精读 | 11 / 4.705331 | 4 / 0.533773 | 0.029710 | hybrid |
| 2 | `...BV1G29EBGE8b...da3915...` | CLI 与 MCP | 19 / 4.401291 | 5 / 0.532788 | 0.028043 | hybrid |
| 3 | `video:bilibili:BV14fTc6TEi5:p1` | Pi Coding Agent | 32 / 3.450673 | 33 / 0.516296 | 0.021622 | hybrid |

## 9. Semantic Paraphrase Demonstrations

### 9.1 `Agent 运行很多轮以后怎样避免上下文越来越长`

[Confirmed Fact]

Lexical top 5：空。Dense/Hybrid top 5：

| Rank | Unit | Title | Dense | Hybrid RRF |
|---:|---|---|---:|---:|
| 1 | `...BV1zSDMBUE5o...ccecc3...` | AI 应用技术串讲 | 0.695538 | 0.016393 |
| 2 | `...BV1TfRfBJEZw...f2dd60...` | Token Efficiency | 0.682764 | 0.016129 |
| 3 | `...BV1iVoVBgERD...e3ecad...` | AI 范式访谈 | 0.654274 | 0.015873 |
| 4 | `...BV1iVoVBgERD...140968...` | AI 范式访谈 | 0.645314 | 0.015625 |
| 5 | `...BV15HXCBkEKY...19a3ee...` | Claude Code 源码分析 | 0.643265 | 0.015385 |

[Observation]

该完整自然语言 query 没有 lexical phrase hit；Hybrid 因而只保留 Dense component，且没有伪造 lexical score。

### 9.2 `怎样让模型在工具执行失败后换一种办法继续完成任务`

[Confirmed Fact]

Lexical top 5：空。Dense/Hybrid top 5：

| Rank | Unit | Title | Dense | Hybrid RRF |
|---:|---|---|---:|---:|
| 1 | `...BV15HXCBkEKY...66a23e...` | Claude Code 源码分析与复刻 | 0.683022 | 0.016393 |
| 2 | `...BV1atjU6KEJF...796808...` | AI 编程中的测试和 Loop | 0.678614 | 0.016129 |
| 3 | `...BV11nSjB2ErQ...9803a9...` | LLM/Agent/RAG 入门 | 0.668932 | 0.015873 |
| 4 | `...BV11nSjB2ErQ...49ac6c...` | 同上 | 0.662907 | 0.015625 |
| 5 | `...BV11nSjB2ErQ...a7a299...` | 同上 | 0.656446 | 0.015385 |

[Observation]

首个 Chunk 的字幕内容直接描述工具失败后把结果反馈给模型、改用下一工具并循环；这是结果内容观察，不是“Dense 已证明更好”的评估结论。

## 10. Timestamp Evidence Demonstration

[Confirmed Fact]

```text
video identity=bilibili:BV15HXCBkEKY:p1
chunk_id=chunk_66a23e51c93b56c062fb8a83a9eedeab
subtitle source=ai
start_time=115.93
end_time=234.01
duration=118.08 seconds
dense_score=0.683022
lexical_score=null
rrf_score=0.016393
```

短摘录：模型使用本地工具搜索，检查失败结果，把失败反馈给模型，再改用下一个工具并持续循环。

Chunk boundaries and timestamp provenance remain unchanged from Stage 1。本轮未增加长 Chunk，也未计算新 jump timestamp。

[Deferred]

```text
Timestamp Anchor Error
= |result jump anchor - manually relevant subtitle time|
```

后续 Eval bucket：`0–15s`、`15–45s`、`45–120s`、`>120s`。

## 11. Metadata Filter Evidence

[Confirmed Fact]

Query=`向量数据库`，filter=`source_db_id=2`：

```text
candidate count before=1547
candidate count after=1543
```

Dense top 3 在过滤后的候选上计算：RAG 源码向量索引 Chunk `0.695682`；RAG 工作机制向量库 Chunk `0.688698`；同 Video 相邻 Chunk `0.663242`。

Hybrid top 3：RAG 工作机制 Chunk（lex rank 1 / dense rank 2 / RRF `0.032522`）；相邻 Chunk（2 / 3 / `0.032002`）；另一相邻 Chunk（7 / 5 / `0.030310`）。

SQL 复用 `RetrievalService._search_filters`，WHERE filter 先选候选，再进行 Dense top-k；Hybrid 两个 component 收到相同 filter。

## 12. No-result and Not-ready

[Confirmed Fact]

合法 query 加不存在的 `folder_id=-999999`：Dense results=0，Hybrid results=0。

临时数据库只初始化 lexical schema、不建 Dense Meta：

```text
Dense:  DenseIndexNotReadyError — dense index not ready; run dense-rebuild
Hybrid: DenseIndexNotReadyError — dense index not ready; run dense-rebuild
```

未就绪不是空结果；Hybrid 未降级为伪 Hybrid 或 Lexical fallback。

## 13. Formal Projection V2 Rebuild

[Confirmed Fact]

第一次 V2 rebuild：

```text
old projection=v3-dense-projection-v1
new projection=v3-dense-projection-v2
total units=1547
embedded=1547
reused=0
stale deleted=0
Video=142
Chunk=1405
duration=25.013624 s
```

全局 projection version 更新，因此一次性重算全部向量；未引入复杂迁移。

第二次 unchanged rebuild：

```text
embedded=0
reused=1547
stale deleted=0
duration=0.766059 s
duplicates=0
damaged=0
```

最终：metadata=FTS=Dense=1547，`integrity_check=ok`，`foreign_key_check=[]`。

## 14. Required Test Commands

[Confirmed Fact]

```text
Command: .venv/bin/python -m pytest tests/test_retrieval.py -q
Exit status: 0
Passed: 13
Failed: 0
Skipped: 0
Warnings: 0 shown

Command: .venv/bin/python -m pytest tests/test_dense_retrieval.py -q
Exit status: 0
Passed: 9
Failed: 0
Skipped: 0
Warnings: 0 shown

Command: .venv/bin/python -m pytest -q
Exit status: 0
Collected/Passed: 310
Failed: 0
Skipped: 0
Warnings: Starlette/httpx deprecation (1); multiprocessing fork deprecation (6 occurrences)
```

标准 full-suite 命令未增加 `PYTHONPATH`，本轮通过。

Dense tests 使用 temporary SQLite、temporary Artifact root 和 fake deterministic provider；覆盖 480-token 预算、字段优先级、hash 内外变化、metadata-only reuse、Projection V2、Chunk 不变、version/hash rebuild、第二次全复用、float32/normalization、filters、not-ready、damage handling、RRF tie-break 和 lazy loading。

## 15. Stage 3 Lifecycle Handoff

[Confirmed Fact]

```text
New or changed product content is not yet automatically synchronized
into Lexical and Dense indexes.

Current available primitives:
- lexical replace_video / delete_video
- dense replace_video / delete_video

Stage 3 must integrate product mutation lifecycle with both indexes.
```

Stage 3 至少覆盖 new favorite completion、subtitle-only completion、ASR completion、summary refinement、Note CRUD、Membership add/remove、last membership removal、subtitle regeneration 和 removed Video cleanup。本轮没有接入这些调用。

## 16. Final Boundary

[Confirmed Fact]

Stage 2 Closure Fix 在此停止。Hybrid 在正式 Retrieval Eval 前保持非默认；Timestamp Anchor Error 延后；未实现 Stage 3、Query Understanding、Search API/UI、formal 20–30 query Eval、reranker、query rewrite/translation、第二 Embedding 模型、长 Chunk、parent-child、segment vector、timestamp refinement、Event consumer、FAISS 或 sqlite-vec。
