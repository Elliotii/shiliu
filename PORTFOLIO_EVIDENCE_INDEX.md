# Shiliu Portfolio Evidence Index

本索引把可以公开陈述的产品能力绑定到实现、测试和运行证据。私人 Source URL、
Corpus 内容、认证数据和 Provider 原始 payload 不属于 Portfolio Evidence。

| Capability | Source implementation | Tests | Eval / runtime evidence | Allowed claim | Known limitation |
|---|---|---|---|---|---|
| Sync | `src/shiliu/sync.py`, `src/shiliu/db.py`, `src/shiliu/bilibili.py` | `tests/test_database_and_sync.py`, `tests/test_v1.py` | `POST_V5_REAL_CORPUS_ONBOARDING_REPORT.md` | Hourly local sync with locks, retry state and complete-snapshot reconciliation | Single-machine process; not high-concurrency distributed sync |
| Backfill / Continuous Sync | `SyncService.drain_history`, membership/history methods in `db.py`, Source UI in `web.py`/`setup.html` | `tests/test_backfill_sync.py` | Safety review + 100/300/full rollout report | Stable time-bound historical expansion is non-destructive and independent from future new favorites | Backlog is intentionally bounded; full materialization may remain pending/manual-ASR-needed |
| Hybrid Retrieval | `src/shiliu/retrieval/` | `tests/test_product_search_api.py`, `tests/test_v4_search_execution.py` | Runtime index consistency and known-item smoke | FTS5 + pinned offline Qwen dense/hybrid retrieval | Local model/index; no vector DB or embedding migration claim |
| Grounded RAG | `src/shiliu/ask/`, `src/shiliu/evidence/` | `tests/test_v4_fast_ask_api.py`, `tests/test_v4_ask_contracts.py` | Ask Fast smoke and retained V4 evidence contracts | Answers are bounded to selected transcript evidence and validated citation IDs | Provider answer latency; insufficient evidence can correctly return no factual answer |
| Timestamp Citation | Evidence materializer, finalizer and shared Evidence UI | `tests/test_v4_context_and_citations.py`, `tests/test_v4_ask_page.py` | Timestamp-navigation smoke | Citations resolve to raw subtitle/ASR time ranges and Bilibili `t=` navigation | Depends on available/current subtitle or ASR timeline |
| Deep Search | `src/shiliu/ask/deep/` | `tests/test_v4_deep_search.py` | Ask Deep smoke and bounded trace | Explicit Deep mode performs bounded navigation/tool rounds before the same grounded finalizer | Not an autonomous open-ended agent; no server-side durable resume for Ask |
| Durable Research | `src/shiliu/research/` | `tests/test_v5_a_stage*` | V5-A closeout reports and runtime smoke | Research operations use durable tasks, attempts, receipts and explicit authorization boundaries | Normal product provider path is intentionally disabled unless explicitly authorized |
| Memory / Persistent Knowledge | Knowledge lifecycle and service under `src/shiliu/research/` | `tests/test_v5_b_stage*` | V5-B closeout reports | Versioned facts, artifacts and topic pages preserve lineage, revalidation and conflict state | Does not autonomously promote model output to truth |
| Personalization | Personal workspace/routing/assistance services | `tests/test_v5_c_stage*` | V5-C closeout reports | Explicit user state can influence routing and presentation with principal/scope fences | No inferred “self-learning” or proactive agent claim |
| Eval / Trace | Stage5, taxonomy audit, Ask traces and frozen eval packages | `tests/test_stage5_integration.py`, `tests/test_v3_5_*`, `tests/test_v5_d_*` | Protected V5 closeout/freeze reports | Deterministic gates, bounded traces and frozen protocol identities support auditable claims | Historical telemetry is incomplete for universal cost/SLA conclusions |
| Cost-aware Model Routing | `AppConfig.model_for`, `Application.provider`, setup API/UI, artifact provenance | `tests/test_v1.py`, `tests/test_pipeline.py` | Post-V5 routing gate + new artifact sidecars | Static Flash ingestion / Pro interactive / independent Pro taxonomy mapping reduces ingestion cost without changing evidence authority | Not a dynamic intelligent router; old artifacts may be `legacy_unknown` |

## Claim boundary

公开材料可以描述为“个人 Bilibili 收藏的证据驱动检索与研究助手”。不得据此声称
large-scale distributed system、production-grade high concurrency、validated
self-improvement、universal multimodal understanding 或通用自主 Agent。
