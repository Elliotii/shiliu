# Shiliu V3 Model Selection Gate Report

Status: **QWEN_EVALUATED — awaiting Version Session review**

This is the required Qwen intermediate decision report. Qwen passed the Hard
Gate, so E5 was not downloaded or tested. No candidate was adopted into the
formal application or formal Dense index.

## 1. Scope and Integrity

**Confirmed Fact** — The experiment used the same 142 Video Units and 1,405
Transcript Chunk Units already present in formal `retrieval_units`. It did not
change unit IDs, chunk IDs, subtitle source, timestamps, Projection V2 field
semantics, chunking, RRF, Product hooks, or the formal embedding model.

**Confirmed Fact** — Candidate vectors were written only to:

```text
/Users/elliot/Library/Caches/Shiliu/model-selection/experiments/qwen3-embedding-0.6b-512.db
```

The formal Dense fingerprint before and after the full build and the 16-query
comparison was identical:

```text
c7b86066a485ec6b0103b52f7df66a98f780a6dd68cd0347c5d061450021db77
```

## 2. Persistent Gate State

Persistent state is stored in `V3_MODEL_SELECTION_STATE.md` using gate version
`v3-model-selection-gate-v1`. The completed transition path was:

```text
PREPARING
→ AWAITING_QWEN_DOWNLOAD
→ QWEN_DOWNLOADED
→ QWEN_SMOKE_COMPLETE
→ QWEN_EVALUATED
```

No E5 phase was entered.

## 3. Baseline

| Field | Baseline value |
| --- | --- |
| Model | `BAAI/bge-small-zh-v1.5` |
| Revision | `46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59` |
| Output | 512-d normalized float32 |
| Projection | `v3-dense-projection-v2` |
| Dense version | `v3-stage2-dense-bge-small-zh-v1` |
| Corpus | 142 Video + 1,405 Chunk = 1,547 |
| Stable cache | `/Users/elliot/Library/Caches/Shiliu/fastembed` |
| Cache size | 91 MiB |
| Offline cold load recheck | 0.337661 s |
| Warm query median | 0.001073 s |
| Full embedding build evidence | 25.013624 s |
| Unchanged reuse rebuild evidence | 0.766059 s |
| Dense DB delta | 5,611,520 bytes |

**Confirmed Fact** — The baseline maps `MCP`, `LangGraph`, `RAG`, and `FAISS`
to the same unknown-token input and exactly identical query vectors. Every pair
has cosine `1.0000001192`, maximum absolute difference `0.0`, and
`Exactly identical=true`. Mixed Chinese-English and Chinese semantic queries
remain distinguishable.

## 4. Candidate Environment

```text
Python: 3.12.13
macOS: 26.5.1 build 25F80
architecture: arm64
physical memory: 25,769,803,776 bytes
free disk at checkpoint: approximately 587 GiB
torch: 2.13.0
transformers: 5.14.1
sentence-transformers: 5.6.0
huggingface-hub: 1.24.0
fastembed: 0.8.0
```

Installation command:

```bash
.venv/bin/python -m pip install -e '.[model-selection]'
```

Selected installed dependency directories total approximately 783 MiB.
`pip check` reported no broken requirements.

## 5. Manual Download Checkpoints

Codex performed metadata lookup and `hf download --dry-run` only. The user
personally executed the real download after the Gate stopped at
`AWAITING_QWEN_DOWNLOAD`.

Dry-run result:

```text
12 files
approximately 1.2G
```

The downloaded snapshot was verified under both `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` before model initialization. No automatic补下载 was
attempted.

## 6. Model Revisions and Cache Paths

| Candidate | Revision | Local path | Actual size |
| --- | --- | --- | ---: |
| Qwen/Qwen3-Embedding-0.6B | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | `/Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B` | 1.1 GiB |
| multilingual-e5-large | Not tested | Not downloaded | — |

The Qwen adapter accepts only an absolute local path, passes
`local_files_only=True`, and requires both offline environment variables.

## 7. Tokenizer / Instruction / Prefix Semantics

Fixed query instruction:

```text
Given a Chinese or English AI and software engineering knowledge retrieval query, retrieve the most relevant evidence passages.
```

Fixed query form:

```text
Instruct: <fixed instruction>
Query: <normalized query whitespace>
```

Documents receive no query instruction. Output uses the first 512 Matryoshka
dimensions and is L2-normalized. Sentence Transformers uses the model-defined
last-token pooling. Input policy is fixed at 512 tokens; Video fields retain
the existing priority and 480-token content budget, while Transcript Chunk
identity and timestamp boundaries remain unchanged.

ASCII tokenizer evidence:

| Query | Token IDs including EOS |
| --- | --- |
| MCP | `44, 7123, 151643` |
| LangGraph | `26223, 11212, 151643` |
| RAG | `49, 1890, 151643` |
| FAISS | `3627, 30849, 151643` |
| Claude Code | `64117, 793, 6119, 151643` |
| Codex | `63691, 327, 151643` |
| OpenAI Agents SDK | `5002, 15469, 50254, 26623, 151643` |

## 8. ASCII Collapse Gate

All vectors were finite, normalized float32 with dimension 512. Norm range was
`0.9999999404–1.0000001192`.

| Pair | Cosine | Max abs difference | Exactly identical |
| --- | ---: | ---: | --- |
| MCP / LangGraph | 0.185416 | 0.185687 | false |
| MCP / RAG | 0.232367 | 0.197706 | false |
| MCP / FAISS | 0.145168 | 0.250839 | false |
| MCP / Claude Code | 0.362997 | 0.181715 | false |
| MCP / Codex | 0.261620 | 0.221912 | false |
| MCP / OpenAI Agents SDK | 0.122191 | 0.234066 | false |
| LangGraph / RAG | 0.505825 | 0.135033 | false |
| LangGraph / FAISS | 0.482556 | 0.154289 | false |
| LangGraph / Claude Code | 0.370162 | 0.168632 | false |
| LangGraph / Codex | 0.228430 | 0.234211 | false |
| LangGraph / OpenAI Agents SDK | 0.377819 | 0.148330 | false |
| RAG / FAISS | 0.579168 | 0.123418 | false |
| RAG / Claude Code | 0.324490 | 0.188860 | false |
| RAG / Codex | 0.351502 | 0.216224 | false |
| RAG / OpenAI Agents SDK | 0.454099 | 0.164440 | false |
| FAISS / Claude Code | 0.297605 | 0.162764 | false |
| FAISS / Codex | 0.257756 | 0.186541 | false |
| FAISS / OpenAI Agents SDK | 0.431591 | 0.157229 | false |
| Claude Code / Codex | 0.453238 | 0.156762 | false |
| Claude Code / OpenAI Agents SDK | 0.287080 | 0.158381 | false |
| Codex / OpenAI Agents SDK | 0.268659 | 0.179806 | false |

**Hard Gate: PASS.** Qwen produced zero identical pairs across all 21 unrelated
ASCII pairings. It resolves the baseline's exact ASCII vector collapse.

## 9. Mixed Chinese-English Probe

Queries:

```text
MCP 协议
LangGraph 状态图 / LangGraph 工作流
RAG 检索增强生成
FAISS 向量索引
Claude Code 上下文压缩
```

Smoke produced zero identical pairs across ten pairings. Maximum cosine was
`0.542055`; minimum pairwise maximum-absolute-difference was `0.133902`.

Direct title/excerpt review of the full top-5 set produced:

| System | Relevant | Partially Relevant | Not Relevant |
| --- | ---: | ---: | ---: |
| Baseline Dense | 9 | 9 | 7 |
| Qwen Dense | 15 | 7 | 3 |
| Current Lexical | 2 | 0 | 0 |

Lexical returned fewer than five results for these phrase queries and returned
none for several natural mixed queries.

## 10. Chinese Semantic Probe

Queries:

```text
Agent 运行很多轮以后怎样避免上下文越来越长
怎样让模型在工具执行失败后换一种办法继续完成任务
如何通过外部资料检索增强模型回答
如何组织可恢复的多阶段 Agent 工作流
```

Smoke produced zero identical pairs. Full top-5 review:

| System | Relevant | Partially Relevant | Not Relevant |
| --- | ---: | ---: | ---: |
| Baseline Dense | 12 | 6 | 2 |
| Qwen Dense | 12 | 7 | 1 |
| Current Lexical | 0 | 0 | 0 |

**Observation** — Qwen preserved Chinese semantic retrieval but did not
uniformly dominate the baseline for every individual ranking. Some top results
remain broad Agent material rather than the exact requested mechanism.

## 11. Full-corpus Build

```text
total units: 1547
Video Units: 142
Transcript Chunk Units: 1405
successful vectors: 1547
failed vectors: 0
dimension: 512
duplicate count: 0
damaged vector count: 0
build duration: 569.049285 seconds
experimental database: 7,032,832 bytes
peak RSS: 634,159,104 bytes
formal Dense unchanged: true
```

## 12. Retrieval Comparison

The frozen set contains seven ASCII, five Mixed Chinese-English and four
Chinese semantic queries. Every query compares Baseline Dense top 5, Qwen
Dense top 5, and Current Lexical top 5 when Lexical results exist.

Aggregate direct-review labels:

| System | Relevant | Partially Relevant | Not Relevant | Returned rows |
| --- | ---: | ---: | ---: | ---: |
| Baseline Dense | 23 | 18 | 39 | 80 |
| Qwen Dense | 46 | 26 | 8 | 80 |
| Current Lexical | 17 | 2 | 7 | 26 |

ASCII-only review:

| System | Relevant | Partially Relevant | Not Relevant |
| --- | ---: | ---: | ---: |
| Baseline Dense | 2 | 3 | 30 |
| Qwen Dense | 19 | 12 | 4 |
| Current Lexical | 15 | 2 | 7 |

Judged by: **Codex Repository Executor**. `Relevant` requires a direct entity or
requested mechanism match in the title/short excerpt; `Partially Relevant`
means the same retrieval domain without the exact target; `Not Relevant` means
unrelated evidence; `Unclear` is used only where no result or insufficient
evidence exists.

The complete 16-query, per-result evidence—including unit ID, unit type, title,
Chunk timestamp, score, short excerpt and allowed judgment label—is in:

```text
research/v3_model_selection/qwen_retrieval_comparison.md
```

## 13. Runtime and Resource Comparison

| Dimension | Baseline | Qwen | E5 if tested |
| --- | ---: | ---: | ---: |
| Output dimension | 512 | 512 | Not tested |
| Model disk size | 91 MiB | 1.1 GiB | Not tested |
| Cold load | 0.337661 s | 47.257571 s | Not tested |
| Warm query embed | 1.073 ms median | 34.030 ms median | Not tested |
| Full embedding build | 25.013624 s | 569.049285 s | Not tested |
| Unchanged reuse rebuild | 0.766059 s | Not measured | Not tested |
| Peak memory | 273,121,280 B recheck | 634,159,104 B | Not tested |
| ASCII collapse | Yes, exact | No, 0/21 identical | Not tested |
| Mixed-query result | Distinct; 9 Relevant / 25 | 15 Relevant / 25 | Not tested |
| Chinese semantic result | 12 Relevant / 20 | 12 Relevant / 20 | Not tested |
| Integration complexity | Existing | Medium: torch/ST local offline provider | Not tested |

**Observation** — Qwen's quality gain has a material cold-start, disk and full
build cost. These are not deterministic blockers on the tested 25.8 GiB Apple
Silicon host, but adoption should preserve lazy loading and stable local cache.

## 14. Timestamp Evidence Boundary

Candidate storage copies `unit_id`, `chunk_id`, `video_id`, `source_type`,
`start_time`, and `end_time` from formal `retrieval_units`. The same 1,405
Transcript Chunks were embedded; no Chunk was split, merged or expanded. Qwen's
long-context capability was not used to alter evidence boundaries.

## 15. Risks and Limitations

1. This Gate is a controlled selection experiment, not a formal Retrieval Eval.
2. Labels are a single Codex title/excerpt review, not independent human relevance judgments.
3. Qwen ranking still contains noise, especially for broad MCP and context-compression queries.
4. Qwen is approximately 12x the baseline model disk footprint and dramatically slower to load/build.
5. MPS behavior was stable in this run but was tested on one Apple Silicon host.
6. No E5 evidence exists because Qwen passed the defined Hard Gate.
7. Formal Product adoption, lifecycle performance and fresh-mutation indexing under Qwen were not tested because adoption is out of scope.

## 16. Recommended Model

```text
Recommend Qwen adoption
```

Rationale: Qwen eliminated the baseline's exact ASCII collapse, completed the
entire unchanged corpus with finite normalized 512-d vectors, materially
improved reviewed ASCII/Mixed top-5 relevance, retained Chinese semantic
performance, and remained operational within local resource limits.

This recommendation does not automatically adopt Qwen. Version Session may
accept it, request additional evidence, or retain the baseline with explicit
Lexical routing.

## 17. Adoption Changes Required

A separately authorized `V3 Model Adoption Patch` would need to:

1. Add a formal local-only Qwen provider with stable cache and lazy loading.
2. Define a new formal model ID/revision, projection/index version and 512-d MRL semantics.
3. Preserve the fixed query instruction and 512-token input policy.
4. Rebuild formal Dense vectors once under explicit authorization.
5. Revalidate Stage 3 replace/delete/reconcile behavior and failure states.
6. Preserve the existing Chunk/timestamp boundary, Lexical index, RRF and Product hooks.

None of these changes were made in this Gate.

## 18. Stop Boundary

Qwen passed the Hard Gate, so the Gate stops at `QWEN_EVALUATED`. E5 was not
downloaded. The formal model, Dense index version, provider, vectors, Stage 3
hooks, Hybrid default and Product surface remain unchanged. Stage 4, Query
Understanding and formal Retrieval Eval were not started.
