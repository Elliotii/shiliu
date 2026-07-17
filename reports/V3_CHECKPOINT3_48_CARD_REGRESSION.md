# V3 Checkpoint 3 — 48-card Regression

Date: 2026-07-17

## Boundary

- Run ID: `1`
- Snapshot: `#2`
- Snapshot hash: `<private-snapshot-hash>`
- Discovery cards: 48 eligible cards, two batches of 24
- Trial Assignment: the same 48 cards plus all three D-level cards
- Formal Discovery A/B/C was not started.

## Final result

The final Draft passed the deterministic Quality Gate after one targeted
Consolidation correction. The two completed local Discovery batches were never
rerun.

### Content Types

| Node | Name | Supporting cards |
|---|---|---:|
| `ct_01` | 教程与操作演示 | 16 |
| `ct_02` | 观点与经验分享 | 17 |
| `ct_03` | 项目演示 | 2 |
| `ct_04` | 评测 | 2 |
| `ct_05` | 论文精读与技术解析 | 3 |
| `ct_06` | 工具与资源推荐 | 3 |

### Domain tree

| Level | Node | Name | Supporting cards |
|---|---|---|---:|
| L1 | `d_01` | AI编程工具与环境 | 9 |
| L1 | `d_02` | AI编程与系统工程方法论 | 10 |
| L2 | `d_02_01` | 规范驱动开发 | 1 |
| L2 | `d_02_02` | RAG与知识检索系统 | 2 |
| L1 | `d_03` | 大模型训练与架构 | 4 |
| L1 | `d_04` | 求职与职业发展 | 10 |
| L1 | `d_05` | 开发环境与命令行 | 1 |

Counts: 6 Content Types, 5 primary Domains and 2 subdomains.

## Quality Gate

- Passed: yes
- Invalid supporting IDs: 0
- Entity leakage: 0
- Content-Type leakage: 0
- Deterministic sibling support-overlap pairs: 0
- All primary and child Domain IDs were inspected by the independent Validator.

Non-blocking warnings retained for later cross-run comparison:

1. `d_02` may be missing an `Agent评测体系` subdomain, but the current local
   evidence is only one card.
2. `d_05` has only one supporting card and may be too narrow for a primary
   Domain.
3. `d_05` is much narrower than its sibling primary Domains.

The initial Draft was blocked because `d_05` incorrectly absorbed `C050` (Pi
Coding Agent configuration). Quality retry routed to Consolidation, corrected
the support mismatch, and retained completed local batches.

## Trial Assignment and Novelty Pool

- Assignments: 51
- High certainty: 34
- Medium certainty: 7
- Low certainty: 10
- Successfully assigned without rejection: 41
- Novelty Pool: 10
- Rejection distribution: 10 `insufficient_evidence`; all other rejection
  reasons 0

The Novelty Pool IDs are `C003`, `C030`, `C042`, `C070`, `C075`, `C079`,
`C082`, `C085`, `C086`, and `C112`.

## Recovery evidence

- The first local batch produced a structurally invalid Topic shape. Its raw
  response and Repair response were saved; after a compatibility fix, resume
  parsed the saved Repair output without replaying the 24-card request.
- The first Hierarchy Validator result omitted child IDs. Quality retry reran
  only Hierarchy Validation.
- A Validator retry returned an empty response. Resume retried only that
  Validator request.
- A real content-support problem routed retry to Consolidation. Both local
  Discovery batches remained completed with their original outputs.
- Consolidation Repair failure exposed that quality feedback was previously
  process-local. Feedback is now reloaded from the persisted Quality result so
  prompt hashes remain stable across restarts.
- Schema failure never replayed the complete compact corpus; JSON Repair used
  raw response + validation error + compact schema.

## Usage and elapsed time

Known persisted usage across original calls and JSON Repair calls:

- Prompt tokens: 94,773
- Completion tokens: 71,965
- Known total: 166,738
- Prompt cache hits: 22,912
- Known model-call elapsed time: 924.566 seconds (about 15m25s)
- End-to-end wall time: about 22m43s, including code fixes, tests and manual
  resume intervals

One empty Validator response occurred before retry-attempt history was
preserved. Its top-level audit fields were overwritten by the successful retry,
so the true total is **at least 166,738 tokens**, not an exact total. The audit
layer now preserves per-attempt usage and latency, and a recovery test verifies
that empty-response usage is included in combined stage metrics. The missing
historical value cannot be reconstructed without inventing data.

## Deviations and decision

- The regression found more protocol drift than synthetic tests: harmless
  local Topic IDs, empty `children` on leaf nodes, and an unsupported Entity.
  These are normalized without weakening the two-level Domain constraint or
  allowing unsupported candidates into the Draft.
- The first final-result estimate during the run referred to the pre-correction
  Draft. The authoritative final result is 6 / 5 / 2 and Novelty Pool 10.
- Classification quality and recovery granularity passed this checkpoint.
- Exact usage for this one historical empty response is unavailable; future
  retries are fully audited after the fix.
- Checkpoint 4 (formal Discovery A/B/C) remains stopped pending review of this
  report and the unexpectedly high regression cost.
