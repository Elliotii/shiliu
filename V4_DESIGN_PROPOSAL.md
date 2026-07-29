# Shiliu V4 Design Proposal

Status: `goal_1_complete`
Date: `2026-07-29`
Scope: `Shiliu V4 only`

## 1. Purpose

V4 turns the existing V0–V3.5 product, Retrieval, and Evidence assets into two
user-complete capabilities:

```text
快速回答
→ Complete Grounded RAG

深入搜索
→ Independent Agentic Search
```

Both modes share one Grounded Answer, Timestamp Citation, Evidence display, and
product response contract.

This document freezes the V4 product and architecture direction needed to begin
implementation. It does not freeze individual prompts, exact Tool names,
LangGraph node names, Eval case counts, or performance thresholds.

## 2. Design principles

```text
继承技术资产
不继承治理重量

先完成纵向闭环
再根据真实失败增加机制
```

Hard rules:

- Raw subtitle or ASR segments are the only authoritative factual evidence.
- Title, description, AI summary, user notes, and cleaned transcript are
  navigation-only materials.
- Fast RAG and Deep Search must not maintain separate Answer or Citation
  implementations.
- Independent Agentic Search must not require Candidate Builder, Fine Selector,
  Mechanical Gate, or the historical Semantic Judge.
- Runtime never reads Eval Gold.
- Provider work remains a minimal DeepSeek extension, not a general LLM SDK.
- LangGraph remains an orchestration shell; Domain and Tool services remain
  framework-independent.

## 3. Product shape

### 3.1 Entry points

V4 adds:

```text
GET /ask
```

The page has an explicit mode selector:

```text
快速回答 | 深入搜索
```

The existing:

```text
GET /search
```

remains the direct Evidence Library search, manual verification, debugging, and
Demo comparison surface.

`/ask` reuses the existing transcript evidence cards, expandable evidence
windows, and Bilibili timestamp jump behavior. It must not create a second
independent Search UI foundation.

### 3.2 Shared Ask product contract

Both modes return the same product shape:

```yaml
run_id: string
mode: fast | deep
status: complete | partial | insufficient

answer_blocks:
  - text: string
    citation_ids: [string]

citations:
  - citation_id: string
    citation_identity_version: string
    video_id: integer
    bvid: string
    title: string
    source_type: human | ai | asr | unknown
    source_language: string
    source_artifact_id: string
    source_version: string
    timeline_run_id: string
    segment_ids: [string]
    start_time: number
    end_time: number
    quote_text: string
    jump_url: string

limitations: [string]

termination_reason:
  answer_ready |
  budget_exhausted |
  no_new_evidence |
  repeated_search |
  provider_error |
  evidence_unavailable

trace_summary: object
```

`answer_blocks` are the only source of the rendered final answer. V4 does not
keep a second free-form `answer` field or a parallel `claims` fact source.

Goal 1 applies the stricter deterministic rule that every non-empty
`answer_block` must contain at least one allowed Citation ID. Titles, status
explanations, and unsupported limitations are represented by the UI,
`status`, and `limitations`; they are not uncited Answer Blocks.

`status` expresses answer sufficiency. `termination_reason` expresses why the
runtime stopped. They must never be conflated.

Expected combinations include:

| status | typical termination reason | meaning |
|---|---|---|
| `complete` | `answer_ready` | available transcript evidence supports the material answer |
| `partial` | `answer_ready` | a useful subset is supported and limitations are explicit |
| `partial` | `budget_exhausted`, `no_new_evidence`, `repeated_search` | some useful evidence exists, but search stopped with material gaps |
| `insufficient` | `evidence_unavailable` | no usable current transcript evidence is available |
| `insufficient` | `provider_error` | the run cannot produce a supported answer |

### 3.3 Response delivery

- Final answers are returned as one structured response.
- Token-by-token answer streaming is not required in V4.
- Internal progress events may be emitted for Deep Search.
- Live progress delivery is an integration enhancement and cannot block the
  core answer loop.

## 4. Reused baseline

### 4.1 Retrieval

Directly reused:

- `SearchRequest` and `ProductSearchRequest`;
- FTS5 Lexical Retrieval;
- Qwen Dense Retrieval;
- RRF Hybrid Retrieval;
- deterministic Auto routing;
- Retrieval filters;
- Retrieval index lifecycle and incremental reconciliation;
- Raw Search Trace;
- Product Search grouping, overfetch, evidence windows, and metadata.

The Fast RAG factual retrieval path uses:

```text
scope = transcript_chunk
```

Navigation may use `scope = video`, subject to the source-aware projection
defined below.

### 4.2 Authoritative Evidence

Directly reused:

- `SourceArtifactReference`;
- Source Artifact and Source Version identity;
- Timeline Run and Segment identity;
- raw subtitle validation;
- exact Retrieval Chunk replay and mapping;
- same-timeline and contiguous-segment assertions;
- live-current index/source binding;
- Bilibili timestamp URL construction.

### 4.3 Product and Provider

Directly reused:

- FastAPI/Jinja/SQLite/filesystem runtime;
- existing DeepSeek configuration and Keychain handling;
- `OpenAICompatibleProvider` HTTP and basic typed error handling;
- existing Search evidence-card rendering and timestamp jump behavior.

## 5. Shared domain contracts

### 5.1 Search execution

V4 introduces a thin internal value representing one already-completed
Retrieval execution:

```yaml
SearchExecution:
  request:
  raw_response:
  product_response:
```

The existing `ProductSearchService.search_with_raw()` already produces the
required Raw and Product responses in one execution.

The V4 Evidence materialization boundary accepts `SearchExecution`; it does not
accept a Query and does not invoke Retrieval.

This corrects the current coupling in:

```text
EvidenceSearchService.search_library(request)
```

where search and Evidence mapping happen inside one method. Compatibility may
be preserved, but V4 orchestration must use the split boundary:

```text
execute search once
→ materialize that execution
```

For Multi-query, each distinct query is executed at most once. Results are
deduplicated and fused after execution using Retrieval Unit and authoritative
Evidence identity.

### 5.2 Navigation document

Navigation is a thin projection over current DB and Artifact data:

```yaml
NavigationDocument:
  video_id:
  bvid:
  title:
  uploader:
  description:
  summary:
  user_notes:
  cleaned_transcript:
  folder_context:
  active_revision:
  source_labels:
  retrieval_provenance:
  authority: navigation_only
```

Initial source policy:

| source | navigation | citation | initial priority |
|---|---:|---:|---|
| title | yes | no | high |
| description | yes | no | medium |
| AI summary conclusion/key points/entities | yes | no | high |
| user notes | yes | no | low |
| cleaned transcript | yes | no | low |
| summary chapter | yes | no | navigation enrichment only |

The first implementation reuses the existing `video` Retrieval Unit for broad
candidate recall, then projects and labels allowed fields for the Agent.

No independent Navigation Index is built in V4 unless real runs show that
post-retrieval source projection cannot recover from mixed-field ranking or
candidate occupancy.

### 5.3 Transcript evidence span

Both Fast RAG and Deep Search consume one authoritative evidence contract:

```yaml
TranscriptEvidenceSpan:
  citation_id:
  citation_identity_version:
  video_id:
  bvid:
  title:
  source_type:
  source_language:
  source_artifact_id:
  source_version:
  source_version_authority:
  timeline_run_id:
  segment_ids:
  segment_ordinals:
  start_time:
  end_time:
  quote_text:
  jump_url:
  parent_chunk_ids:
  retrieval_provenance:
```

Goal 1 defines:

```text
CITATION_IDENTITY_VERSION = "v4-citation-identity-v1"
```

`citation_id` is a versioned stable hash of:

```text
citation_identity_version
source_artifact_id
source_version
timeline_run_id
ordered segment_ids
```

It must not contain Query, rank, retrieval method, Candidate Builder method, or
parent Search Candidate identity.

Canonicalization is deterministic:

- segments share one Source Artifact, Source Version, and Timeline Run;
- segments are ordered by authoritative Segment ordinal, never by opaque
  Segment ID text;
- ordinals are strictly increasing, duplicates are rejected, and spans that
  claim continuity must remain contiguous;
- the ordered Segment IDs are serialized with the existing canonical JSON
  convention.

The Window Reader may expand a mapped Chunk with bounded adjacent segments only
when:

- all segments share one `source_artifact_id`;
- all segments share one `source_version`;
- all segments share one `timeline_run_id`;
- ordinals remain ordered and contiguous;
- character and duration budgets are satisfied.

The Citation identity binds only the final Segment set admitted into factual
Answer Context. Extra before/after Segments shown when a user expands an
Evidence card are display context and do not change Citation identity.

### 5.4 Stale evidence

If a Retrieval Hit cannot bind to the current Source Version:

```text
do not materialize Citation
→ record stale evidence in Trace
→ skip the Hit
→ continue with other Hits or searches
```

Stale Evidence never enters:

- `TranscriptEvidenceSpan`;
- Answer Context;
- `answer_blocks`;
- final Citation display.

Before final response construction, every used Citation is revalidated against
its Source Version. If all otherwise relevant evidence is stale or unavailable:

```yaml
status: insufficient
termination_reason: evidence_unavailable
```

Index repair is not performed implicitly by the Ask runtime.

## 6. Complete Grounded RAG

Fast RAG remains a normal Service Pipeline and does not use LangGraph.

### 6.1 Runtime flow

```text
AskRequest(mode=fast)
→ one Query Analysis call
→ original Query + bounded rewrites
→ one SearchExecution per distinct query
→ Evidence materialization
→ deduplication / lightweight fusion
→ Transcript-only Context construction
→ one Grounded Answer call
→ deterministic Schema and Citation validation
→ optional one structured-output repair
→ repeat the complete deterministic validation
→ final Source Version revalidation
→ shared AskResponse
```

Budget envelope:

```yaml
query_analysis_calls: 1
answer_calls: 1
repair_calls: max_1
iterative_search: false
```

The Query Analysis output may include:

- normalized user intent;
- bounded search rewrites;
- exact entities and useful aliases;
- language;
- filters copied from the product request.

It must not decide Evidence sufficiency or fabricate expected answer facts.

### 6.2 Context construction

The factual model input contains:

- the original user Query;
- normalized intent where useful;
- only validated `TranscriptEvidenceSpan` objects;
- stable Citation IDs;
- explicit instruction that navigation materials are unavailable as evidence;
- an output schema and allowed Citation ID list.

It does not contain:

- AI summary text;
- description;
- user notes;
- cleaned transcript;
- AI chapter summary;
- stale or unmapped Retrieval Hits;
- Eval Gold.

Context construction performs:

- deduplication by Citation/Segment identity;
- deterministic rank-only fusion across distinct Query executions;
- deterministic ordering by fused relevance and video/time;
- per-span and total character/token budgets;
- bounded same-source merging;
- explicit truncation records in Trace.

Automatic iterative context compaction is deferred.

### 6.3 Runtime validation

Online validation is deterministic only:

- every referenced Citation ID exists in the current Evidence Context;
- every Citation has current Source Version and valid Segment lineage;
- every non-empty Answer Block has at least one allowed Citation ID;
- no answer block references a navigation-only source;
- Citation time bounds reconstruct from the referenced Segments;
- final Citation order is stable and duplicate-free.

No runtime Semantic Judge is used.

Semantic claim-support quality is evaluated offline with a small V4 Eval set.
Runtime does not claim it can detect or split a semantically half-supported
Block.

### 6.4 Repair and fail-closed behavior

Goal 1 permits at most one Answer repair call. The repair receives the same
Query, the same factual Evidence Context, the allowed Citation IDs, and
deterministic validation errors.

Repair may correct structure or regenerate Answer Blocks from that same
Evidence. It may not retrieve again, introduce a new Citation, mechanically
replace an unknown Citation with an arbitrary allowed ID, or add facts absent
from the Evidence Context.

The repaired output runs through the complete Schema, Citation, Identity,
Version, Segment, and time-bound validation again. If it remains invalid, Goal
1 returns:

```yaml
status: insufficient
answer_blocks: []
termination_reason: provider_error
```

The first version does not salvage a subset of valid Blocks after a failed
repair. Block salvage and finer sentence/claim granularity are reconsidered
only after Vertical Slice evidence shows that the stricter behavior materially
harms useful answers.

## 7. Independent Agentic Search

### 7.1 Framework decision

Deep Search uses low-level LangGraph `StateGraph` as a thin orchestration layer.

Allowed:

- explicit state;
- nodes;
- conditional edges;
- bounded loop;
- state progress events.

Forbidden in V4:

- checkpointer or persistence;
- durable resume;
- Memory;
- HITL or interrupt;
- subgraph;
- Multi-Agent;
- LangGraph Cloud;
- LangSmith runtime dependency;
- prebuilt `create_agent`.

All Retrieval, Navigation, Transcript, Evidence, Answer, budget, and validation
logic remains framework-independent. LangGraph nodes may only adapt State to
these services and return State deltas.

### 7.2 Runtime state

The Deep Search state must express at least:

```yaml
run_id:
query:
filters:

open_questions: []
resolved_questions: []

evidence_spans: []
visited_video_ids: []
visited_segment_ids: []
previous_queries: []

decision_rounds: 0
tool_calls: 0
consecutive_no_new_evidence: 0

started_at:
last_action:
last_observation_summary:
errors: []
termination_reason:
```

`open_questions` and `resolved_questions` are a runtime worklist for Planning
and Replanning. They are not Gold Aspects, Eval Gates, or annotation targets.

### 7.3 Agent actions and tools

DeepSeek returns a Pydantic-validated structured Action. Native Tool Calling is
not required.

The exact Tool names remain an implementation detail, but the framework-neutral
service capabilities are:

- read navigation information for selected videos;
- search navigation/video candidates;
- search raw transcript chunks;
- read an authoritative mapped transcript window;
- read bounded adjacent segments;
- finish with current Evidence;
- stop without an answer when Evidence remains unavailable.

Tool results separate:

```text
navigation observation
vs
authoritative TranscriptEvidenceSpan
```

Only `TranscriptEvidenceSpan` is accumulated in `evidence_spans`.

### 7.4 Deterministic budgets and stops

Initial hard envelope:

```yaml
agent_decision_rounds: max_6
tool_calls: max_12
answer_calls: 1
repeated_query_stop: true
no_new_evidence_stop: true
focused_video_limit: 8
consecutive_no_new_evidence_limit: 2
window_default_each_side: 2
window_max_each_side: 4
final_evidence_context_chars: 12000
total_runtime_seconds: 360
search_phase_cutoff_seconds: 150
final_answer_reserve_seconds: 210
```

Deterministic runtime code, not the Prompt, enforces:

- maximum Decision Rounds;
- maximum Tool Calls;
- normalized repeated Query detection;
- repeated Segment detection;
- consecutive no-new-Evidence limit;
- Context Budget;
- total runtime deadline.

The Agent may recommend an action, but the runtime guard decides whether it is
allowed.

The 360-second total deadline covers the complete Deep request, including final
answer generation. New decisions and Tools may not start after the 150-second
search cutoff. If usable Evidence exists, the runtime moves to shared answer
finalization and preserves up to 210 seconds for the initial answer and the
existing bounded same-context repair. V4 Structured Provider calls must be
bounded by the remaining monotonic deadline; this does not change Fast defaults
or historical Provider call semantics.

Stop mapping:

| condition | termination reason |
|---|---|
| worklist resolved with usable Evidence | `answer_ready` |
| decision/tool/time/context budget reached | `budget_exhausted` |
| bounded consecutive actions add no Evidence | `no_new_evidence` |
| normalized searches repeat without progress | `repeated_search` |
| DeepSeek cannot continue | `provider_error` |
| only stale/unreadable Evidence remains | `evidence_unavailable` |

After stopping, the shared Grounded Answer service determines `complete`,
`partial`, or `insufficient` from the available Evidence and explicit
limitations. The Agent orchestration does not implement a second answer path.

## 8. DeepSeek runtime

### 8.1 Provider boundary

V4 reuses the existing:

```text
OpenAICompatibleProvider
existing DeepSeek base URL
existing Keychain API key
existing configured DeepSeek model
```

The minimal V4 extension supports:

- general messages rather than prompt-only calls;
- Pydantic structured output with response metadata;
- logical runtime roles;
- per-role timeout, thinking, sampling, and output budget;
- bounded retry for retryable transport errors;
- at most one bounded structured-output repair where allowed;
- usage, latency, finish reason, retry, and error Trace fields.

It does not become a provider-neutral SDK.

### 8.2 Logical roles

Initial logical roles:

| role | use | initial behavior |
|---|---|---|
| `query_analysis` | Fast RAG understanding/rewrite | structured, thinking off, deterministic, short output |
| `agent_action` | Deep Search Action selection | structured, thinking off, deterministic, short output |
| `grounded_answer` | shared final answer | structured Answer Blocks and Citation IDs |

The roles may initially use the same configured DeepSeek model. Separate role
names exist for Prompt, timeout, budget, and later evidence-driven tuning, not
to trigger a new Provider selection.

The historical Codex CLI Semantic Judge is not wired into any V4 runtime
service.

## 9. Trace

V4 records one lightweight event stream and exposes two projections.

### 9.1 User trace summary

The default product layer may show:

- current search target;
- videos examined;
- transcript Evidence found;
- why search continued;
- why the run answered, partially answered, or stopped;
- total latency;
- final Citation sources.

### 9.2 Developer trace

The expandable layer may show:

- Query Understanding and rewrites;
- Agent Action and bounded observation summaries;
- Tool timeline and parameters;
- Replanning;
- decision/tool counters;
- token usage;
- latency;
- stale Evidence;
- errors;
- deterministic guard decisions;
- termination reason.

Trace is not a general Observability Dashboard. Persistent Trace should favor
IDs, hashes, bounded summaries, and metrics rather than copying full subtitle
corpora or sensitive user data.

## 10. Work classification

### 10.1 `must_build`

- shared Ask request/response contract;
- `/ask` product entry with explicit Fast/Deep modes;
- Fast RAG Query Analysis and bounded rewrite flow;
- one-execution Retrieval boundary;
- authoritative Transcript Evidence materialization;
- Transcript-only Context Builder;
- stable Citation contract;
- shared Grounded Answer with Answer Blocks;
- deterministic Citation Runtime Validation;
- framework-independent Navigation and Transcript access services;
- bounded Deep Search State and structured Action;
- thin LangGraph `StateGraph` orchestration;
- deterministic budgets and stop behavior;
- shared Evidence display for both modes.

### 10.2 `in_goal_support`

- minimal DeepSeek Provider messages/role/metadata extension;
- bounded Provider retry and structured-output repair;
- source-aware Navigation projection over existing candidates;
- Window Reader and bounded adjacent-segment access;
- stale Evidence skip and Trace;
- Multi-query result deduplication/fusion;
- lightweight shared Trace events and two projections;
- extraction/reuse of existing Search evidence-card rendering;
- typed V4 API errors;
- focused deterministic tests and a few real end-to-end runs.

### 10.3 `deferred`

- token-by-token answer streaming;
- Native Tool Calling;
- independent Navigation Index;
- Reranker;
- automatic Adaptive Router between Fast and Deep;
- Runtime Semantic Judge;
- automatic iterative Context Compaction;
- generalized LLM SDK;
- general Observability Dashboard;
- persistent Memory;
- Checkpoint/Resume;
- durable long-running research;
- HITL/Interrupt;
- Multi-Agent or Subgraphs;
- LangGraph Cloud or LangSmith runtime dependency;
- generalized Eval platform;
- V5 personalization or proactive behavior.

## 11. Three vertical Goals

### Goal 1: Complete Grounded RAG

User value:

> A user asks a question about the collection and receives a transcript-grounded
> answer with timestamp citations.

Included:

- shared Ask contracts;
- Fast RAG Query Analysis and bounded rewrites;
- one-execution Search boundary;
- Evidence materialization and stale handling;
- versioned and canonical Stable Citation identity;
- factual Evidence Span versus display-context separation;
- Context Builder;
- DeepSeek role extension needed by Fast RAG;
- Grounded Answer, one bounded repair, and deterministic Citation validation;
- Fast Ask API;
- focused service/API tests.

Not included:

- LangGraph;
- Agentic iterative search;
- final polished `/ask` UI;
- large Eval expansion.

### Goal 2: Independent Agentic Search

User value:

> A user chooses Deep Search and the system navigates videos, searches and reads
> raw transcript windows, replans, and stops within a visible budget.

Included:

- framework-independent Navigation projection;
- transcript search/window/neighbor capabilities;
- structured DeepSeek Agent Action;
- explicit Deep Search State;
- thin LangGraph `StateGraph`;
- deterministic budget and stop guards;
- Evidence accumulation;
- shared Grounded Answer reuse;
- Agent Trace events;
- focused loop, Tool, stop, and integration tests.

Not included:

- Checkpointer;
- Memory;
- HITL;
- Native Tool Calling;
- independent Navigation Index unless a real documented failure forces
  reconsideration.

### Goal 3: Product Integration, Lightweight Eval, and Demo

User value:

> Both Ask modes are usable from one product page, expose evidence and trace, and
> are demonstrated with retained successes and failures.

Included:

- `/ask` page and Fast/Deep selector;
- reuse of existing Search evidence cards and timestamp jumps;
- user and developer Trace projections;
- progress events when they fit without blocking delivery;
- a small historical/real Query regression set;
- groundedness, Citation validity, Agent stop, latency, cost, and failure review;
- targeted refinement driven by observed failures;
- README and Demo update;
- V4 final integration and concise implementation handoff.

Not included:

- a general Eval platform;
- exhaustive or sealed V3.5-style governance;
- automatic routing;
- production SLA claims.

## 12. Acceptance direction

Exact thresholds and case counts are intentionally not frozen yet.

V4 acceptance must demonstrate:

- Fast RAG returns useful Answer Blocks with valid transcript citations;
- every returned Answer Block has an allowed Citation;
- Deep Search operates independently of Candidate Builder;
- Deep Search changes actions based on observations;
- deterministic budgets and stop reasons work;
- stale Evidence never enters Citation;
- partial and insufficient outcomes remain visible;
- both modes use identical Answer/Citation response contracts;
- `/ask` reuses existing evidence presentation;
- serious Unsupported Claims are retained and analyzed;
- latency, DeepSeek usage, Tool calls, and limitations are reported;
- deterministic tests pass.

## 13. Main risks and mitigations

| risk | mitigation |
|---|---|
| mixed video Unit produces misleading navigation candidates | source-aware projection first; independent index only after real failure |
| display excerpt is mistaken for authoritative context | materialize exact raw Segments before Context construction |
| source changes after Retrieval | bind current version, skip stale Hits, revalidate final Citations |
| Candidate ID changes with retrieval path | use source-derived stable Citation ID |
| Multi-query repeats Retrieval | one `SearchExecution` per distinct query, materializer never searches |
| display expansion changes Citation identity | bind identity to factual Segment set, not UI-only context |
| malformed repair introduces new claims | one same-context repair, full revalidation, then fail closed |
| Agent repeats searches or reads | deterministic normalized Query and Segment visited sets |
| LangGraph leaks into Domain | framework-independent services and thin node adapters |
| Provider latency or malformed JSON | role budgets, bounded retry/repair, typed termination |
| Context grows without bound | deterministic Context Budget and evidence deduplication |
| V4 recreates V3.5 governance | lightweight offline Eval and three vertical Goals only |

## 14. Deferred reconsideration triggers

The following are reconsidered only after a recorded real failure:

- independent Navigation Index: mixed-field ranking causes material miss or
  unrecoverable candidate occupancy;
- Reranker: fused Retrieval repeatedly returns relevant evidence below usable
  Context capacity;
- Native Tool Calling: structured Action is demonstrably unreliable or blocks
  a required DeepSeek capability;
- token streaming: final-answer latency makes the product unusable despite
  progress events;
- Context Compaction: bounded Evidence Context cannot support the required Deep
  Search workload.

## 15. Next action

The design and Goal 1 research integration are approved. Goal 1 completed
implementation, deterministic/full regression verification, real DeepSeek
Vertical Slice validation, and Main Session Integration Review on 2026-07-29.
Goal 2 completed implementation, deterministic/full regression verification,
real DeepSeek Vertical Slice validation, a bounded Integration Repair, and Main
Session Integration Acceptance on 2026-07-29. The next action is:

```text
discuss and approve the bounded Goal 3 product, lightweight Eval, and Demo plan
before preparing a Goal 3 Execution Prompt
```

Goal 3 must integrate the accepted Fast and Deep backends without creating a
new Answer, Citation, Navigation, Trace, Tool, Policy, or Eval platform.
