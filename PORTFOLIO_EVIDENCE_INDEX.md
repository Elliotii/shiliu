# Shiliu Portfolio Evidence Index

本索引把可以公开陈述的产品能力绑定到实现、测试和运行证据。私人 Source URL、
Corpus 内容、认证数据和 Provider 原始 payload 不属于 Portfolio Evidence。

| Capability | Source implementation | Tests | Eval / runtime evidence | Allowed claim | Known limitation |
|---|---|---|---|---|---|
| Sync | `src/shiliu/sync.py`, `src/shiliu/db.py`, `src/shiliu/bilibili.py` | `tests/test_database_and_sync.py`, `tests/test_v1.py` | Public synthetic tests | Hourly local sync with locks, retry state and complete-snapshot reconciliation | Single-machine process; not high-concurrency distributed sync |
| Backfill / Continuous Sync | `SyncService.drain_history`, membership/history methods in `db.py`, Source UI in `web.py`/`setup.html` | `tests/test_backfill_sync.py` | Public synthetic tests | Stable time-bound historical expansion is non-destructive and independent from future new favorites | Backlog is intentionally bounded; full materialization may remain pending/manual-ASR-needed |
| Hybrid Retrieval | `src/shiliu/retrieval/` | `tests/test_product_search_api.py`, `tests/test_search_orchestration.py` | Public unit/integration tests | FTS5 + pinned offline Qwen dense/hybrid retrieval | Local model/index; no vector DB or embedding migration claim |
| Grounded RAG | `src/shiliu/ask/`, `src/shiliu/evidence/` | `tests/test_v4_fast_ask_api.py`, `tests/test_v4_ask_contracts.py` | Public contract tests | Answers are bounded to selected transcript evidence and validated citation IDs | Provider answer latency; insufficient evidence can correctly return no factual answer |
| Timestamp Citation | Evidence materializer, finalizer and shared Evidence UI | `tests/test_v4_context_and_citations.py`, `tests/test_search_page.py` | Public UI/contract tests | Citations resolve to raw subtitle/ASR time ranges and Bilibili `t=` navigation | Depends on available/current subtitle or ASR timeline |
| Deep Search | `src/shiliu/ask/deep/` | `tests/test_v4_deep_search.py` | Public bounded-trace tests | Explicit Deep mode performs bounded navigation/tool rounds before the same grounded finalizer | Not an autonomous open-ended agent; no server-side durable resume for Ask |
| Durable Research | `src/shiliu/research/` | `tests/test_v5_a_stage*` | Public deterministic tests | Research operations use durable tasks, attempts, receipts and explicit authorization boundaries | Provider-backed execution requires explicit local authorization and credentials |
| Knowledge Draft / lineage | Draft and knowledge lifecycle services under `src/shiliu/` | `tests/test_v5_6_goal2b_knowledge_draft.py`, selected `tests/test_v5_b_stage*` | Public deterministic tests | Immutable Draft revisions preserve Answer Snapshot, Citation/Evidence mapping, limitations and explicit confirmation boundaries | Candidate prose has a known semantic-source defect; high-quality materialization and durable-Knowledge-native reuse are not accepted V5.6 capabilities |
| Personalization | Personal workspace/routing/assistance services | `tests/test_v5_c_stage*` | Public deterministic tests | Explicit user state can influence routing and presentation with principal/scope fences | No inferred “self-learning” or proactive agent claim |
| Eval / Trace | Stage5, taxonomy audit and Ask traces | `tests/test_stage5_integration.py`, selected self-contained eval tests | Public schemas, protocols and synthetic tests | Deterministic gates, bounded traces and frozen protocol identities support auditable claims | Private corpora and Provider runtime records are intentionally excluded |
| Cost-aware Model Routing | `AppConfig.model_for`, `Application.provider`, setup API/UI, artifact provenance | `tests/test_v1.py`, `tests/test_pipeline.py` | Public routing tests | Static Flash ingestion / Pro interactive / independent Pro taxonomy mapping reduces ingestion cost without changing evidence authority | Not a dynamic intelligent router; old artifacts may be `legacy_unknown` |

## Claim boundary

公开材料可以描述为“个人 Bilibili 收藏的证据驱动检索与研究助手”。不得据此声称
large-scale distributed system、production-grade high concurrency、validated
self-improvement、universal multimodal understanding 或通用自主 Agent。
