# Shiliu V3 — Stage 4B Anchor Boundary Closure Report

## 1. Scope and Stop Boundary

**Classification:** `Accepted with Follow-up`

This closure examined and minimally fixed only the ASCII technical-entity boundary used by Stage 4B jump-anchor enrichment. The implementation change is limited to `src/shiliu/retrieval/enrichment.py`; the test change is limited to `tests/test_search_enrichment.py`.

No Search Planner, query classification, routing, fallback policy, retriever, grouping, ranking, temporal merge, chapter enrichment, Qwen Provider, index, Product source, API schema, Web UI, Stage 5, or Stage 6 behavior was changed.

## 2. Read-only Anchor Map

| # | Actual module / function | Current logic found before the fix | Boundary assessment | Minimal closure change |
|---|---|---|---|---|
| 1 | `src/shiliu/retrieval/enrichment.py:240` — `EvidenceEnricher._anchor_window` | This is the actual jump-anchor resolver. It initializes Chunk-start fallback, scans raw subtitle segments in the current Evidence Window, and applies the priority chain. | Correct module and scope. | No structural change. |
| 2 | `enrichment.py:264–288` — `EvidenceEnricher._anchor_window`, Priority 1 | `_normalize(normalized_query) in _normalize(segment.content)` selected `exact_query_phrase`. | Unsafe for a single ASCII entity: `RAG` matched `storage`; this path ran before Priority 2. | Route exact entities and the ASCII core of mixed phrases through the shared boundary matcher. |
| 3 | `enrichment.py:377–402` — `_best_term_match`, `_term_match_count`, Priority 2 | `_normalize(term) in view`, with `view.count(...)` for coverage. | Unsafe; no ASCII boundary check. | Count ASCII technical terms through the shared boundary implementation. |
| 4 | `enrichment.py:355–374` — `_ascii_terms`, `_query_terms`, `_unique_terms` | ASCII spans/terms are extracted, then CJK sequences are added; NFKC/casefold is used only for deduplication while the original trimmed term is retained. | Extraction was deterministic but did not make matching safe. | Add leading-dot token support for `.NET`; preserve all other extraction behavior. |
| 5 | `enrichment.py:23–31` — `_ASCII_TOKEN_PATTERN`, `_ASCII_TERM`, `_ASCII_SPAN` | ASCII tokens allowed letters/digits plus internal `. _ : / + -`, terminal `++` and `#`; multi-token spans were whitespace-joined tokens. | Covered `C++`, `C#`, `GPT-5`, and Qwen versions; did not extract a leading-dot `.NET` query as one token. | Add the explicit leading-dot form. |
| 6 | `enrichment.py:277–281,355–357` — `_ascii_terms` / `matched_terms` | `C++`, `C#`, `GPT-5`, and `Qwen3-Embedding-0.6B` remain literal extracted terms. | Representation was preserved and suitable for explicit boundary logic; generic `\b` would not be suitable. | No lexer or third-party parser added. |
| 7 | `enrichment.py:344–351,377–402` — `_contains_query_phrase`, `_best_term_match` | Chinese full phrases used normalized substring containment; CJK keyword terms used substring counts. | Existing Chinese semantics were intentional and not part of the ASCII defect. | Keep Chinese phrase/coverage semantics unchanged. |
| 8 | `enrichment.py:309–310` — `_normalize` | `NFKC` → `casefold` → whitespace split/collapse/join. | Correct and retained. | None. |
| 9 | `enrichment.py:377–392` — `_best_term_match` | A tuple of original query terms with non-zero match counts becomes `matched_terms`, capped to eight when applied. | Unsafe only because ASCII counts were substring counts. | Preserve original values/order; change only ASCII match counting. |
| 10 | `enrichment.py:240–306` — `_anchor_window`, `_apply_anchor` | Priority 1 sets `exact_query_phrase/high`; Priority 2 sets `exact_entity_term/high`; Priority 3 sets `keyword_overlap/medium`; otherwise the initialized Chunk-start fallback remains. | Enumerations and confidence policy were correct. | No enum, confidence, jump-time, or fallback change. |

## 3. Existing Matching Behavior

Before this closure, both high-confidence paths depended on ordinary normalized substring containment:

```python
# Priority 1
query_view in _normalize(segment.content)

# Priority 2
_normalize(term) in view
```

Therefore Priority 1 was only substring containment, and Priority 2 had no independent technical-entity boundary. `RAG`, `AI`, `MCP`, and versioned entities could be accepted inside longer ASCII alphanumeric strings. C++/C#/GPT-5 were represented correctly as terms, but representation alone did not provide boundary safety.

## 4. Identified Boundary Risk

The risk was real rather than hypothetical. On the formal raw-subtitle corpus, the pre-fix substring rule found occurrences rejected by the fixed boundary rule:

| Query | Substring occurrences | Safe occurrences | Rejected embedded occurrences |
|---|---:|---:|---:|
| `RAG` | 91 | 84 | 7 |
| `AI` | 1,999 | 1,601 | 398 |
| `MCP` | 101 | 98 | 3 |
| `GPT-5` | 1 | 1 | 0 |

If such a segment was inside the candidate Evidence Window, the old Priority 1 could label the embedded occurrence `exact_query_phrase` with high confidence. The automated fixtures also prove the unsafe cases even when a specific string is absent from the formal corpus.

## 5. Implemented Boundary Semantics

`contains_technical_entity(normalized_segment, normalized_entity)` now uses a shared deterministic occurrence counter. It does not use `\b`.

For an ASCII entity containing a letter:

- normalize segment and entity with the existing NFKC → casefold → whitespace-collapse order;
- the left side must be the string start or not an ASCII letter/digit;
- the right side must be the string end or not an ASCII letter/digit;
- an entity beginning with `.` may match after an alphanumeric character, deliberately allowing `.NET` in `ASP.NET`;
- an entity ending with `++` may be followed by digits, deliberately allowing `C++20`;
- punctuation such as Chinese punctuation, parentheses, whitespace, and `-` is a valid external delimiter.

The helper returns false for empty, non-ASCII, or letterless values. Non-ASCII phrase and CJK keyword matching remains on the existing deterministic substring logic.

## 6. Priority 1 `exact_query_phrase` Safety

Priority 1 now calls `_contains_query_phrase`:

- `exact_entity`: the complete normalized query must pass `contains_technical_entity`;
- `mixed_entity`: the complete normalized phrase must occur and every extracted ASCII term in it must independently pass the same technical boundary rule;
- Chinese and other keyword phrases retain full normalized substring behavior.

Consequently `query=RAG, segment=storage` can no longer become `exact_query_phrase/high`. A mixed phrase such as `MCP 协议` cannot hide an embedded `MCP` inside `XMCP 协议`.

## 7. Priority 2 `exact_entity_term` Safety

`_best_term_match` still preserves the existing coverage, frequency, earliest-start, and segment-index tie-breaks. Its ASCII count now calls the same `_technical_entity_match_count` used by `contains_technical_entity`. CJK count behavior remains unchanged.

Thus Priority 2 cannot reintroduce a high-confidence substring match after Priority 1 rejects it. `matched_terms` still contains the original extracted query values and `_apply_anchor` still caps it to eight entries.

## 8. Symbol-ending Entity Handling

The behavior is fixed by tests rather than by generic word-boundary regexes:

| Entity | Accepted examples | Rejected / decision |
|---|---|---|
| `C++` | `C++`, `C++ 项目`, `（C++）`, `C++20` | `C++20` is accepted as a language-standard form. |
| `C#` | `C#`, `C# 开发`, `（C#）` | `ABC#DEF` does not match `C#`. |
| `.NET` | `.NET`, `.NET Core`, `ASP.NET` | `ASP.NET` is accepted by the current product decision. |
| `GPT-5` | `GPT-5`, `GPT-5 API`, `（GPT-5）`, `GPT-5-based` | `GPT-50`, `XGPT-5`, and `GPT-5X` are rejected. |
| Qwen version | standalone, model suffix, parentheses | leading/trailing ASCII-alphanumeric extensions are rejected. |

## 9. Negative Test Evidence

Parameterized helper tests reject all required embedded forms:

- `RAG`: `storage`, `drag`, `storage engine`, `paragraph`;
- `AI`: `train`, `detail`, `maintain`, `email`;
- `MCP`: `XMCPY`, `preMCP2`;
- `GPT-5`: `GPT-50`, `XGPT-5`, `GPT-5X`;
- `OpenAI`: `MyOpenAIClient`, `OpenAI2`;
- Qwen version: prefixed and suffixed alphanumeric extensions;
- `C#`: `ABC#DEF`.

Anchor-level parameterized tests additionally prove that RAG/AI/MCP/GPT-5/OpenAI segments containing only those negative strings retain `chunk_start_fallback/fallback`, never either high-confidence source.

## 10. Positive Test Evidence

Parameterized helper tests accept the required standalone, punctuation, parenthesized, hyphen-separated, Chinese-adjacent, symbol-ending, and versioned forms for:

```text
RAG, AI, MCP, GPT-5, C++, C#, .NET, Qwen3-Embedding-0.6B
```

The existing exact-phrase integration test also runs through `EvidenceEnricher` for OpenAI, MCP, C++, C#, GPT-5, and the Qwen version and confirms a raw-segment-start high-confidence anchor.

## 11. Anchor Integration Tests

The formal `EvidenceEnricher` entry path is covered, not only the helper:

- `RAG`: skips `storage engine`, selects the later `这里介绍 RAG 检索` segment at 9 seconds, source `exact_query_phrase`, confidence `high`;
- `AI`: negative-only segments never produce a high-confidence anchor;
- `MCP 工作方式`: Priority 2 skips `XMCPY protocol`, selects the real MCP segment at 8 seconds, source `exact_entity_term`;
- `MCP 协议`: skips the embedded form and selects `MCP 协议的工作方式` at 12 seconds;
- Chinese `上下文压缩`: retains `exact_query_phrase/high` at the raw segment start;
- semantic question: retains `chunk_start_fallback` and no segment anchor;
- window-only scanning, raw segment start, chapter non-overwrite, grouping, temporal consolidation, API, and Presentation Trace behavior remain covered by the Stage 4B and regression suites.

## 12. Formal Corpus Probe

The probe used the 130 raw subtitle JSON files currently declared by the formal Product database: 65,234 segments, zero missing or malformed files in the probe.

Literal corpus presence:

| String | Segments | Videos | Evidence disposition |
|---|---:|---:|---|
| `storage` | 1 | 1 | Present; old `RAG` substring logic could mis-anchor, fixed rule rejects the embedded occurrence. |
| `drag` | 0 | 0 | No formal sample; automated fixture proves rejection. |
| `train` | 120 | 9 | Present; old `AI` substring logic could mis-anchor, fixed rule rejects embedded occurrences. |
| `detail` | 4 | 2 | Present; old `AI` substring logic could mis-anchor, fixed rule rejects embedded occurrences. |
| `maintain` | 0 | 0 | No formal sample; automated fixture proves rejection. |
| `XMCPY` | 0 | 0 | No formal sample; automated fixture proves rejection. |
| `GPT-50` | 0 | 0 | No formal sample; automated fixture proves rejection. |

The fixed-code aggregate comparison is shown in section 4. For reproducibility without exposing subtitle text, the first rejected formal occurrences were recorded only as `(video_id, BVID, segment_index)`:

- RAG: `(6, BV1o87764Ebs, 256)`, `(39, BV1hr6EBBEhM, 700)`, `(71, BV1co9yBhEvW, 64)`, `(103, BV1rQ9JBoECh, 243)`, `(121, BV1BJ4m1e7g8, 29)`;
- AI: `(1, BV1zDTX6eEGu, 92)`, `(4, BV1FPTT6uEd2, 2)`, `(4, BV1FPTT6uEd2, 5)`, `(6, BV1o87764Ebs, 2)`, `(6, BV1o87764Ebs, 98)`;
- MCP: `(7, BV14fTc6TEi5, 621)`, `(47, BV1kMVt6mEgr, 332)`, `(93, BV15HXCBkEKY, 597)`.

## 13. Product Search Smoke

All searches used the real Product Search API. This smoke assesses anchor boundaries only, not relevance ranking.

| Query | Trace ID | Raw / groups / windows | Anchored result summary | Suspicious substring anchor |
|---|---|---|---|---|
| `RAG` | `ddeb7132-e3ad-479e-af1b-35ff93e9ebef` | 50 / 10 / 10 | 10 high anchors; top sampled jump times 1194.6, 8.71, 6.5, 201.759, 406.46; source `exact_query_phrase`, matched `RAG`. | None. |
| `AI` | `8d584c8b-2534-465a-9e75-639a3f2d44c4` | 50 / 10 / 12 | 10 high anchors matched `AI`; 2 windows correctly retained fallback. | None. |
| `MCP` | `0703274f-c490-4ba2-a114-c3b7dec8f253` | 50 / 10 / 16 | 16 high anchors matched `MCP`. | None. |
| `GPT-5` | `40ffb943-c0da-43ca-8834-379b092f3220` | 8 / 7 / 1 | One high `exact_query_phrase` anchor at 139.733, matched `GPT-5`. | None. |
| `C++` | `3461a751-cb65-4bd8-9711-64b59aa84a3a` | 3 / 3 / 0 | No formal subtitle window to anchor; positive fixtures prove boundary handling. | None. |
| `C#` | `daa6e571-c6e5-45b2-b825-2eab667875c2` | 0 / 0 / 0 | No formal result; positive fixtures prove boundary handling. | None. |

Searches added six allowed Raw Search Traces and six linked Product Presentation Traces. They did not mutate Product or index tables.

## 14. Regression Tests

| Exact command | Exit | Passed | Failed | Skipped | Warnings |
|---|---:|---:|---:|---:|---:|
| `.venv/bin/python -m pytest tests/test_search_enrichment.py -q` | 0 | 75 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_product_search_api.py -q` | 0 | 11 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_search_consolidation.py -q` | 0 | 10 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest -q` | 1 | 484 | 1 | 0 | 1 |
| `env -u NO_PROXY -u no_proxy -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u http_proxy -u https_proxy .venv/bin/python -m pytest -q` | 0 | 485 | 0 | 0 | 1 |
| same controlled environment, `.venv/bin/python -m pytest` | 0 | 485 | 0 | 0 | 1 |

The required unmodified full-suite command was executed. Its sole failure was unrelated to repository behavior: the execution environment supplied a `NO_PROXY` value containing raw IPv6 `::1`; httpx 0.28 interpreted it as `all://::1` and raised an invalid-port error in `test_output_budget_exhaustion_is_not_retryable`. Removing only proxy environment variables produced a complete 485-test pass without adding `PYTHONPATH` or changing code. The one warning is the pre-existing Starlette/httpx deprecation warning.

## 15. Data and Index Integrity

Formal pre-/post-smoke Product Source hashes were identical:

| Table | Rows | SHA-256 before | SHA-256 after |
|---|---:|---|---|
| `videos` | 144 | `2177b07d3789aab203aecdc9f60c21a367c70375612ebe78a22391b6c51bc504` | identical |
| `video_notes` | 1 | `4acacc0cd3723d2698e9af4a1646953b09a2697baa565f894e6b85c1ad43077f` | identical |
| `favorite_sources` | 2 | `66070fc4cfe49e1bb763c82c4b2f127c138c46ed354132b8ad6f02cb4f66f833` | identical |
| `video_source_memberships` | 146 | `a07601365feefd767142bec75b69dccfd6839083872014b21e20fb5270f6943e` | identical |
| `events` | 273 | `7148a77d40e04807b7c27d7c35d5f6413357c84847e14c8fcbe3ae66534b66f4` | identical |

Index state before and after:

```text
retrieval_units:         1,555 → 1,555
retrieval_units_fts:     1,555 → 1,555
retrieval_dense_vectors: 1,555 → 1,555
retrieval_search_traces: 48 → 54
retrieval_search_presentations: 18 → 24
PRAGMA integrity_check: ok
PRAGMA foreign_key_check: 0 rows
```

Only the explicitly allowed trace tables changed.

## 16. Remaining Limitations

- Timestamp Anchor Error measurement remains deferred to Stage 6 Retrieval Eval.
- Long-duration Evidence Window presentation remains a Stage 5 / Stage 6 follow-up.
- Formal relevance quality has not been evaluated; the Product smoke proves boundary behavior only.
- The `.NET` exception intentionally accepts a leading alphanumeric host such as `ASP.NET`; it is a narrow product rule, not a general lexer.
- `C++` followed by digits is intentionally accepted; other entity-specific suffix semantics are not inferred.

No remaining limitation blocks Stage 5 planning.

## 17. Recommended Classification

```text
Stage 4B: Accepted with Follow-up
Stage 5: Ready for Planning
Stage 6: Not Started
```

Acceptance evidence is complete: both high-confidence paths share safe ASCII technical-entity boundaries; required negative and positive cases pass; C++/C#/.NET/version forms are fixed by tests; Chinese and semantic fallback semantics remain intact; 485 tests pass in the corrected execution environment; Product/index integrity is unchanged apart from allowed bounded traces.

Follow-up is limited to Timestamp Anchor Error evaluation, long-window presentation, and formal relevance evaluation. This closure does not begin Stage 5 or Stage 6.
