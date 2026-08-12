# Shiliu Post-V5 Bounded Repair Closeout

Date: 2026-08-12 (Asia/Shanghai)

## Identity and scope

- Frozen baseline: `codex/post-v5-product-closeout` at
  `5f1bf4dd899e97583a234b224e209f8c6aac9294`.
- Isolated repair branch: `codex/post-v5-bounded-repair`.
- Final implementation checkpoint HEAD: `0bdb4c79ea67d8563deceac45d98500316dfb1dc`.
  The branch's handoff HEAD also contains this closeout document and is reported by the
  final repository verification; the document-only commit does not alter implementation.
- Scope/semantics authority: `POST_V5_REAL_USE_REPAIR_TRIAGE.md`.
- Execution authority: `POST_V5_BOUNDED_REPAIR_CHARTER.md`.
- Detailed package evidence: `POST_V5_BOUNDED_REPAIR_CHECKPOINTS.md`.

The authorized order was preserved: Goal A → Goal C → Goal B → Goal D. This was a
bounded Post-V5 repair, not V6. The implementation did not introduce a schema migration,
retrieval/embedding/chunk redesign, new execution architecture, Provider-backed Research,
frontend rewrite or generic platform.

## Package outcomes

| Goal | Checkpoint | Outcome |
|---|---|---|
| A — Ask Finalization Reliability | `93c96b5a642a9524c48c96252fd533fa914e3f7f` | PASS — Provider/runtime generation failure, evidence insufficiency and evidence unavailability are distinct; one recovery is allowed only for output-budget/empty-output failure. |
| C — Real-corpus Library Scaling | `58c889ce9e0e97961c45e77271fc90d36417de53` | PASS — 40-card snapshot-bounded keyset pages replace full-corpus render; Ask Enter/Shift/IME behavior is explicit and tested. |
| B — Terminal Candidate Disclosure | `951b468` | PASS — terminal candidates are bounded, reconstructed from durable Search lineage and remain non-authoritative; Citation Authority is unchanged. |
| D — Restricted Research Boundary | `0bdb4c79ea67d8563deceac45d98500316dfb1dc` | PASS — deterministic kernel success is not projected as user-level objective completion without registered evaluator authority; stale terminal semantics and durable derivation confirmation are fixed. |

Goal D-UX implemented the bounded plain-language “doing / found / why stopped / next”
summary. Default-collapsing the existing V5-B/V5-C workspace and diagnostics sections was
dropped as optional out-of-bounds work because it would require broader information-
architecture/workspace redesign. D-Core is complete.

## Repaired failure families

1. A successful retrieval followed by Provider/runtime answer failure no longer renders
   as `证据不足`. `execution_outcome` distinguishes `answer_generated`,
   `generation_failed`, `evidence_insufficient` and `evidence_unavailable` without
   changing the v16 persisted `answer_status` contract.
2. Grounded Answer keeps the normal Pro/thinking-enabled path. Only
   `output_budget_exhausted` and `empty_model_output` receive exactly one Pro/thinking-off
   recovery over the same evidence and deadline; network/auth/config/deadline failures do
   not recover.
3. The library no longer renders/enriches the entire real corpus before first paint.
   Stable keyset traversal uses an insertion high-water boundary and exact multi-folder
   membership identity; a forward sync cannot duplicate pre-existing cross-folder cards.
4. Terminal Ask now discloses up to five candidates by default (hard maximum eight) from
   at most 12 durable child Search traces. Missing exact unit/window identity is stale,
   never substituted; metadata leads have no transcript identity/excerpt; adopted
   Citations are excluded.
5. Research keeps raw kernel history unchanged while projecting user truthfully. A
   deterministic no-Provider `valid_success` is a limited mechanical output unless the
   active Goal's objective and every semantic constraint use server-registered evaluator
   authority.
6. Terminal product projection removes exactly the two known obsolete pre-audit
   limitation forms after an Outer Audit exists, while immutable raw artifacts retain
   their original text.
7. Branch and Replay disclose their permanent derived-Task effect. Both the UI and public
   API require explicit confirmation; false/cancel paths write no derivation.

## Verification

Final deterministic suite, run with the local macOS Keychain backend disabled so the
non-live suite cannot discover credentials or dispatch a Provider:

```text
PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring \
PYTHONPATH=src python -m pytest

1821 passed, 4 deselected, 1 warning in 152.36s
```

The four deselections are the repository's explicit `external_artifact` /
`live_provider` exclusions from the deterministic default. The warning is the existing
FastAPI TestClient/httpx deprecation warning.

Package evidence in the checkpoint record includes:

- Goal A: 76 focused Ask tests plus 37 H0/Continuation nearby regressions.
- Goal C: 59 library/Ask/web/source/backfill tests and mutation/performance traversal.
- Goal B: 88 Ask/Search/persistence regressions after the bounded authority re-review.
- Goal D: 193 Research/nearby regressions; 28 focused completion/provider-product tests.
- Python compilation, Research JavaScript syntax and `git diff --check` passed at the
  relevant gates.

Original-failure regressions cover Fast/Deep answer-generation failure, model-declared
insufficiency, stale/zero evidence, output-budget recovery, cross-folder forward-sync
mutation, missing transcript identity after restart, metadata-only leads, registered and
unregistered Research evaluators, stale audit prose, and Branch/Replay false-confirmation
non-write behavior. Nearby Citation, Evidence, persistence, personalization, source and
control contracts remain green in the full suite.

## Independent reviews

- Pagination complexity review found one High cross-folder forward-sync duplication
  path. The cursor was narrowed to a membership row high-water boundary with derived
  source positions; the sole bounded re-review found no Blocking/High/Medium.
- Fresh Ask-stack/Citation Authority review found one High: a persisted presentation with
  a window but no exact chunk identity could be projected as current. The bounded repair
  requires exact unit plus full window identity, tightens metadata non-authority and adds
  restart regression; the sole bounded re-review recommended PASS.
- Fresh Research semantic review found one High stale Outer Audit synonym and a
  list/detail evaluator-authority inconsistency. The narrow projection/test fixes preserve
  raw records; the sole bounded re-review found no Blocking/High/Medium and recommended
  Goal D PASS.

No reviewer was used to redesign a package, and no review finding expanded frozen scope.

## Before/after measurements and durable smoke IDs

### Ask

| Path | Before | After bounded repair |
|---|---|---|
| Fast natural answer | `ask_run_0eabf36f514f40a382cc15bbdc1ff3f3`, 55.6 s total | `ask_run_0a4a00d56a3a42d580a697e97770d12c`, `answer_generated`, 76.20 s total, five Citations |
| Deep natural answer | `ask_run_917e153e8c9a4e59a2bc24b4dc7e2005`, 80.4 s total | `ask_run_2173c642c9234e03a88db4639977c020`, `answer_generated`, 69.71 s total |
| Honest insufficiency | ambiguous pre-repair product copy | Fast `ask_run_3cefac1ebc394ea0ad8f5aacb8b03b15` and Deep `ask_run_02d0729c82614490ba6d9ab69da145a6`, both `evidence_insufficient` |

The final no-Provider natural smoke produced two durable checks while its report was
collected:

- Ask run `ask_run_3e54e22365a448feb12d062687adf1bf`, Search trace
  `e70977fa-66d3-40c9-b4c0-8e5ff64aab6d`, 0.050 s.
- Ask run `ask_run_1b417701e200464798dc1fb217341b3d`, Search trace
  `5cd16a4c-e0d3-4586-8e01-9f337073d10a`, 0.063 s.

Both completed through the normal Fast Ask product service as `evidence_unavailable`,
with zero answer blocks, Citations and candidates. This is the required honest empty
path, not a fabricated success. The Keychain backend was disabled and no network
Provider was called.

### Library

| Measurement | Before RU-012 | After |
|---|---:|---:|
| Active memberships measured | 2,055 | 2,209 |
| Initial cards | 2,055 | 40 |
| Initial HTML | 8,465,186 bytes | 199,013 bytes |
| Warm local response completion | 8.69 s | 0.355 s |
| Second page | n/a | 292,741 bytes / 0.336 s |

### Candidate reconstruction

Historical durable Ask/Search lineage was reconstructed without live mutation:

- RU-011 Fast insufficient `ask_run_1046902129f64af190b4d08797ef9f69`:
  18 unique / five visible candidates.
- RU-011 Fast Provider failure `ask_run_4bc7cddeef64416da75d9f103339ad6d`:
  14 unique / five visible candidates.
- RU-013 Deep insufficient `ask_run_cb58ead1fabf46d8a14f44336d251db6`:
  nine unique / five visible, first item an explicit metadata-only lead.

### Restricted Research

Natural task `rtask_9b6de665dc9953db62051d91c08d46af` completed its durable kernel
path with `valid_success / answer_ready`, three mechanical blocks, seven evidence uses,
12 events, six checkpoints, five inner actions, one Outer Audit and 12 command receipts.
The product projection is `limited_deterministic_output`,
`objective_verified=false`; the obsolete pre-audit limitation is absent from current
projection and no Provider boundary was recorded.

## Remaining limitations and deferred items

- Normal Pro Grounded Answer latency remains variable. This repair establishes honest
  failure/recovery semantics, not a latency SLA or a primary thinking-off policy.
- Library cursors are insertion-stable traversal boundaries, not general database
  snapshots. Arbitrary edits/removals of pre-existing membership ordering fields can
  change later page composition.
- Candidate disclosure is bounded current reconstruction, not exact historical UI replay.
  Historical presentation summaries do not archive historical title/body text; missing
  exact current identity is shown stale/unavailable.
- Restricted Research remains deterministic and no-Provider. Provider-backed Research,
  runtime rewrite, new evaluator platform and broader workspace/diagnostics IA remain
  unauthorized.
- Raw Research artifacts remain immutable and may contain stage-local prose that the
  current user product projection correctly reconciles.
- The full suite's local Keychain discovery is an environment concern: deterministic
  verification must keep `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` to avoid
  credential prompts or accidental Provider dispatch. No product behavior was changed to
  accommodate the test host.

Explicitly deferred/rejected work remains deferred: V6, Retrieval/embedding/chunk
redesign, Intent Router, Fast→Deep reuse, Ask/Search history product, progressive
streaming, Evidence Enrichment, new Eval, Provider-backed Research, Multimodal,
Multi-Agent, GraphRAG, new Memory architecture, self-evolution and proactive Agent.

## Portfolio-worthy real failure evidence

- RU-001/RU-004/RU-011 demonstrate why Provider failure must not masquerade as evidence
  insufficiency and why output-budget recovery must be bounded rather than generic.
- RU-012 provides a concrete 8.47 MB / 8.69 s real-corpus first paint reduced to roughly
  0.20 MB / 0.36 s without a frontend or storage rewrite.
- RU-003/RU-011/RU-013 show useful durable retrieval lineage surviving terminal answer
  failure while remaining strictly separate from final Citation Authority.
- RU-007/RU-009/RU-015 show why durable kernel success, user objective completion and
  permanent derived-task controls require separate product semantics.

The bounded repair is ready for handoff. It does not authorize or begin any deferred
feature, new evaluation program, README/resume claim expansion or V6 work.
