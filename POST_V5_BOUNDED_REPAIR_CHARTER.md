# Shiliu Post-V5 Bounded Repair Charter

Date: 2026-08-12 (Asia/Shanghai)

Status: `READY — AWAITING USER EXECUTION AUTHORIZATION`

Baseline: `codex/post-v5-product-closeout` at
`5f1bf4dd899e97583a234b224e209f8c6aac9294`.

Authority source: `POST_V5_REAL_USE_REPAIR_TRIAGE.md`. This Charter sequences the frozen
work; it does not authorize implementation, runtime changes or migration.

## 1. Owner session and scope

Use one Bounded Repair Owner Session to execute, after explicit user authorization:

```text
A — Ask Finalization Reliability
→ C — Real-corpus Library Scaling
→ B — Terminal Candidate Disclosure
→ D — Restricted Research Boundary
```

Do not reopen V6, Retrieval, embeddings/chunks, Deep design, Provider-backed Research,
the eval framework or generalized platform work. A package stops and returns to the
Main Owner/User if acceptance would require schema/platform expansion, Retrieval or Deep
redesign, Research runtime rewrite, frontend rewrite or a new execution architecture.
Optional scope may be dropped rather than expanded.

## 2. Goal A — Ask Finalization Reliability

Execution:

```text
Provider/compatibility/finalizer source audit
→ smallest role-specific generation and finalizer correction
→ deterministic regressions
→ Fast/Deep tests
→ small natural smoke with measurements
→ checkpoint commit/push
```

Gate:

- Provider/runtime generation failure is durably and visibly distinct from evidence
  insufficiency.
- Bounded recovery performs at most one eligible attempt and never fabricates an answer
  or citation.
- Grounded Answer remains `deepseek-v4-pro`; Retrieval, Evidence and Citation Authority
  are unchanged.
- Existing v16 outcome/usage/trace fields are preferred. Any schema proposal requires a
  written necessity justification and a Main-owner/User decision before migration.
- Before/after successful Fast and bounded Deep records include final-answer Provider
  latency, total Ask latency, reasoning/output tokens and Provider calls/retries. There
  is no invented hard SLA and no obvious repair regression; remaining latency is a
  documented limitation.
- No Retrieval, Deep, router, streaming or broad prompt-tuning scope has entered.

Checkpoint records RU-001/RU-004/RU-011, root family, tests, measurements and residual
limitations, then creates one coherent commit and pushes the current repair branch.

## 3. Goal C — Real-corpus Library Scaling

Execution:

```text
ordering/pagination semantics audit
→ stable keyset/cursor implementation preferred
→ bounded SSR integration
→ 2,055-item temporary-DB regression
→ live first/subsequent-page measurements
→ bounded Ask keyboard affordance
→ checkpoint commit/push
```

Gate:

- Initial row count and HTML payload are bounded; live measurements use the same method
  as the observed failure.
- Cursor semantics follow the existing stable ordering tuple.
- Inserting a new top favorite during traversal does not unexpectedly duplicate or skip
  existing rows.
- If bounded offset is used, its trade-off and concurrent-forward-sync test are recorded
  and it is not described as snapshot-stable pagination.
- Folder/view filters, multi-folder cards, Mark, Notes, reading/archive mutations and
  Ask IME/Enter behavior pass regressions.
- No pagination framework, storage layer, service layer or frontend rewrite is added.

Checkpoint records RU-012/RU-014, root family, tests, measurements and any traversal
limitation, then creates one coherent commit and pushes.

## 4. Goal B — Terminal Candidate Disclosure

Goal B starts only after Goal A's outcome semantics are stable.

Execution:

```text
durable Ask→Search lineage audit
→ bounded candidate reconstruction
→ transcript-candidate / metadata-lead projection
→ restart and stale-identity regressions
→ Citation Authority regressions
→ checkpoint commit/push
```

Gate:

- Candidate evidence is never a final citation and metadata-only leads remain
  non-authoritative.
- Provider failure and honest evidence insufficiency can both expose useful completed
  retrieval without changing their distinct terminal semantics.
- Restart behavior is explicitly bounded reconstruction from durable Search identity,
  not exact historical UI replay.
- Unavailable/stale historical video or metadata identity is shown honestly and never
  silently substituted.
- Projection is bounded/deduplicated and adds no new persistence platform.

Checkpoint records RU-003/RU-011/RU-013, root family, tests and reconstruction
limitations, then creates one coherent commit and pushes.

## 5. Goal D — Restricted Research Boundary

Execute D-Core first, then reassess whether D-UX remains bounded.

### D-Core — required

- A deterministic no-Provider extractive result is not projected as user-level
  objective completion.
- Terminal projection removes the stale claim that Outer Audit has not run when it has.
- Long-term Research is visibly Restricted / Experimental.
- Branch/Replay discloses the permanent derived-task side effect and requires explicit
  confirmation before creation.

### D-UX — optional

Within the existing template/page only, prefer plain-language task summary, collapsed
diagnostics and progressive disclosure for advanced controls. Drop D-UX if it becomes a
workspace redesign, frontend rewrite or information-architecture project. A bounded
fallback is entry de-emphasis, Experimental labeling and collapsed Advanced diagnostics.

Gate:

- No false user-level success or stale terminal limitation remains.
- Durable Branch/Replay side effects are explicit before creation.
- Restricted/Experimental boundaries are understandable.
- Historical Research runtime, durable V5 records and Frozen outcomes remain untouched.
- D-Core passes independently; any dropped D-UX item and reason are recorded.

Checkpoint records RU-007/RU-009/RU-015, root family, tests and residual UX limitations,
then creates one coherent commit and pushes.

## 6. Review policy

- After A + B, use one fresh-context read-only Ask-stack reviewer for Provider failure
  semantics, candidate-versus-citation authority, restart reconstruction, Fast/Deep
  consistency and scope creep.
- Use a pagination reviewer only if cursor/order/multi-folder/continuous-sync complexity
  materially rises. Complete bounded regressions are sufficient otherwise.
- After D, use one fresh-context read-only product/semantic reviewer for user-level
  success semantics, Restricted boundary, durable-action affordance and diagnostics
  leakage.
- A reviewer may trigger only a narrow fix and at most one bounded re-review. Reviews do
  not reopen package design.

## 7. Commit, closeout and handoff

Each stable package has one primary rollback-able checkpoint:

```text
A → test → commit/push
C → test → commit/push
B → test → commit/push
D → test → commit/push
```

Every checkpoint records related RU IDs, root failure family, tests and known residual
limitations. Avoid micro-commit churn.

After all authorized packages that remain bounded:

```text
full deterministic suite
+ original-failure regressions
+ small natural smoke
```

The closeout records repaired/deferred families, before/after measurements, new live run
IDs, remaining limitations and portfolio-worthy evidence. It does not start a large
Real-use Eval, update a resume, start V6 or begin deferred features.

## 8. Authorization gate

```text
TRIAGE_CORRECTION_COMPLETE
LONG_RUNNING_REPAIR_CHARTER_READY
AWAITING_USER_EXECUTION_AUTHORIZATION
```

No package execution begins until the user provides that authorization.
