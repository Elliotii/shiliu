# Shiliu V0–V3.5 Final Closeout

Status: `final_repository_packaging_in_progress`  
Closeout date: 2026-07-29  
Scope: V0 through V3.5  
Future-version design or implementation: excluded

This document records only aggregate evaluation facts and artifact identities.
It does not reproduce Eval Query, Gold Aspect/Span, video identifiers, evidence
text, expected labels, Evidence Groups, or per-Case decisions/results.

## 1. Final status

V0–V3.5 is formally closed as a self-contained development baseline:

```yaml
product_foundation: complete_with_documented_limits
v3_taxonomy: research_closed_not_productized
v3_retrieval: formally_closed
v3_5_evidence_sufficiency:
  implementation: implemented
  integration: minimally_product_integrated
  operation: limited_pilot
  evaluation: formally_evaluated_below_target
  maturity: partial
final_answer_generation: not_implemented
agentic_search: not_implemented
```

This is a safe engineering baseline, not a claim that Evidence/Sufficiency has
proven stable daily production use.

## 2. V0–V2 product foundation

V0–V2 established the local product and data pipeline:

- Bilibili favorite-source registration, multi-folder synchronization, and
  incremental/background processing;
- subtitle-first acquisition with bounded ASR fallback;
- raw subtitle, cleaned text, structured summary, and local Artifact storage;
- reading state, Mark, archive, ignore, and user Markdown notes;
- FastAPI/Jinja/SQLite/filesystem product runtime;
- reuse of content and user state when a video appears in multiple folders.

These versions remain the operational foundation for V3 retrieval and V3.5
evidence processing. User databases, full collection contents, and generated
media-derived assets are local product data, not Git source artifacts.

## 3. V3 taxonomy research boundary

The pre-retrieval V3 taxonomy work produced useful domain schemas, evidence,
evaluation practice, and failure analysis. It did not become the primary
product path and is retained as `research-only` history.

The final V3 product direction is Retrieval, not taxonomy generation. Taxonomy
runtime outputs, raw Provider calls, and research work directories are not
future hard dependencies.

## 4. V3 Retrieval closeout

The formal external decision is archived byte-for-byte at
`SHILIU_V3_VERSION_DECISION.md` with SHA-256
`fa6d394926d445ecfc5bfe20a6c2f4586c31adcbc9695dca99fdae9f5e993fa3`.
The repository closeout is `V3_CLOSEOUT.md`.

V3 formally delivers:

- rebuildable and incrementally reconciled Video/Transcript Retrieval Units;
- FTS5 Lexical, Qwen Dense, RRF Hybrid, and deterministic Auto routing;
- structured filters, same-video consolidation, bounded evidence windows, and
  coarse timestamp navigation;
- Product Search API, Web Search, Raw/Presentation Trace, and typed errors;
- snapshot-isolated, pooled/judged formal Retrieval Eval.

The accepted aggregate evaluation covers 24 queries and 452 judgments over a
frozen 144-video, 1,555-unit corpus. Dense/Hybrid pooled Recall@10 was
approximately 0.88 and held-out Recall@10 approximately 0.90. These are
pooled/judged metrics, not exhaustive-corpus relevance claims.

V3 does not claim sentence-precise evidence selection, stable no-answer
rejection, claim–evidence alignment, cited synthesis, or Agentic Search.

## 5. V3.5 Evidence and Sufficiency closeout

V3.5 adds:

- canonical Source Artifact, Source Version, Timeline, Segment, and timestamp
  identity;
- `SearchCandidateSet`, `EvidenceCandidateSet`, and `EvidenceBundle`;
- fixed Candidate Builder and Fine Selector;
- Mechanical Gate structural/operational routing;
- Semantic Sufficiency four-state decisions;
- `POST /api/evidence-sufficiency`, Trace retrieval, and Search UI integration;
- Product Query Set, Development/Frozen split, Gold seals, prediction-first
  isolation, and a formally frozen aggregate evaluation.

F1A and F1B candidate improvements were evaluated and rejected; the formal
Builder and Selector v1 identities were retained. Mechanical Gate R1 was
accepted. Stage 5 received a bounded compatibility/runtime/UI repair and a
current Refreeze without reopening frozen algorithms or historical Eval.

V3.5 aggregate Frozen results:

| Metric | Result |
|---|---:|
| Query count | 10 |
| Retrieval Hit@10 | 1.0 |
| Builder required-span recall | 0.163095 |
| Builder complete-group availability | 0.0 |
| EvidenceBundle required-span recall | 0.025 |
| EvidenceBundle complete-group hit | 0.0 |
| Mechanical routing accuracy | 0.5 |
| Semantic four-state accuracy | 0.2 |
| Runtime error count | 0 |
| Severe false-sufficient count | 0 |

Aggregate primary failure attribution is five Builder-incomplete outcomes and
five Mechanical source-unverifiable outcomes. No Case-level details are
reproduced here.

## 6. Repository reconciliation

### Tracked-change disposition

| Path | Disposition | Reason |
|---|---|---|
| `pyproject.toml` | included | `openai>=2,<3` is required by the formal Semantic Judge integration |
| `src/shiliu/retrieval/__init__.py` | included | `build_bilibili_jump_url` is a formal product/UI navigation helper |
| `scripts/run_stage3r_qc_phase_b_r.py` | restored | the apparent deletion was an exact duplicate move into `research/scripts`; the moved copy computed the repository root incorrectly |
| `src/shiliu/retrieval/orchestrator.py` | included | optional trace persistence is bound by V3.5 runtime evidence |
| V3 product/source/test changes | included | formal V3 and Stage 5 product delivery |
| `V3_CURRENT_STATE.md` | retained and superseded | historical ledger, not current authority |

No tracked modification remains unexplained.

### Regression and collection repair

- `uploader_contains` remains an additive Product filter but is omitted from
  serialized requests when unused, preserving pre-Stage-5 frozen request bytes.
- Regression tests cover both the legacy serialized shape and the normalized
  current `uploader_contains` field.
- `scripts/export_pqs_v1_authoring_packet.py` was restored from its misplaced
  exact implementation so the test suite collects normally.
- Tests requiring the historical external construction workspace or local
  Product database are explicitly marked `external_artifact`.
- Hard-coded Stage 3R `/tmp` corpus references now use the authoritative
  repository corpus.
- Stale phase/hash tests now distinguish historical frozen inputs from later
  accepted/refrozen source state.

### Generated/local artifact policy

Tracked:

- source, tests, version decisions, final reports, aggregate results;
- necessary Seal, dataset/split/Gold Manifest, and small deterministic Fixture;
- formal Case-level Artifact only where required for repository reproducibility,
  referenced by path/hash/access boundary rather than summarized.

Excluded without deleting user data:

- personal SQLite databases and full favorites/content directories;
- Provider state databases and raw logs;
- model caches and virtual environments;
- bulk unredacted Trace, candidate dumps, and incomplete work files;
- temporary exports, compiled files, and tool caches.

No raw representative Trace is included because none met the strict redaction
boundary. Trace contracts, seals, aggregate results, and minimal tests remain.

## 7. Final test baseline

```yaml
deterministic_core:
  command: .venv/bin/python -m pytest
  passed: 1405
  failed: 0
  collection_errors: 0
  deselected_external: 4
  clean_staged_index_export_verified: true

external_or_environment_dependent:
  markers:
    - external_artifact
    - live_provider
  default_suite_excludes: true
  requirements_documented: true

historical_failure_whitelist: []
```

Targeted final results:

- Retrieval: 67 passed;
- Evidence/Sufficiency: 61 passed;
- API/Stage 5: 44 passed;
- minimal in-process Smoke: 6 passed.

No new paid Provider call was required. The historical live-provider smoke
remains bound by the Stage 5 seals.

The sole current warning is a non-failing Starlette/httpx TestClient
deprecation.

## 8. Authoritative artifacts

Top-level authorities:

- `SHILIU_V3_VERSION_DECISION.md`
- `V3_CLOSEOUT.md`
- `V3_5_FINAL_CLOSEOUT.md`
- `V3_5_FINAL_CLOSEOUT.json`
- `V3_5_FINAL_FREEZE_SEAL.json`
- `STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json`
- `SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.md`
- `SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.json`

The Repository Manifest records exact paths and SHA-256 values. Case-level Eval
assets are never expanded in this Closeout.

## 9. Known limitations

- V3 relevance evaluation is pooled/judged rather than exhaustive.
- V3.5 Builder/Selector coverage is below target; the fixed implementations are
  historical baselines and should not become mandatory future hard dependencies.
- Semantic Judge latency remains high.
- Production proxy timeout configuration is outside the repository.
- Evidence/Sufficiency has limited-pilot rather than proven daily-use maturity.
- Final Answer generation, Agentic Search, Memory, Harness, and automatic
  evidence remediation are not implemented.

## 10. Final commit and handoff status

```yaml
content_baseline_commit: CONTENT_BASELINE_COMMIT_PENDING
manifest_packaging_commit: SELF
branch: codex/v3-domain-completion
expected_final_working_tree: clean
self_contained_commit: pending_final_git_packaging
safe_for_continued_development: pending_final_git_packaging
```

The Repository Manifest records the content-baseline parent commit. The final
packaging commit is represented as `SELF`, because a Git commit cannot contain
its own hash. This section is finalized after the content-baseline commit is
created and verified.
