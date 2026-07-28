# Shiliu V3.5 Stage 3B — Candidate Robustness and Structured Fine Selector

## 1. Result

**Provider / Schema Reliability Blocker**

Stage 3B implementation and Development evaluation are complete. The bounded generic Candidate Builder experiment was negative, and the Structured LLM selector was both less accurate and insufficiently reliable. `preferred_selector: deterministic` for V3.5 Development.

## 2. Scope Compliance

Only Candidate Builder acronym robustness, ID-only structured fine selection, deterministic Bundle reconstruction, Development evaluation, tests, traces, state, and reporting were performed. V3 Search/ranking/router/RRF/chunk policy, Gold, Snapshot, Raw artifacts, Stage 3A assets, API/UI, Sufficiency, final answers, Held-out evaluation, and V4 were not modified or run.

## 3. Repository Before / After

Before: branch `codex/v3-domain-completion`, HEAD `8287c8d92378b87290274d02605cdc704cb8c470`, ahead 1, with extensive pre-existing tracked and untracked work. The exact pre-state is outside the repository at `/tmp/shiliu_v3_5_stage3b_before/repository_before.txt`.

Stage 3B intended changes are limited to `V3_5_CURRENT_STATE.md`, this report, `research/v3_5/stage3b/**`, `src/shiliu/evidence/stage3a.py`, `src/shiliu/evidence/stage3b.py`, `src/shiliu/eval_v3_5/stage3b.py`, and `tests/test_v3_5_stage3b_selector.py`. Pre-existing tracked modifications were preserved. Unexpected Stage 3B changes: none detected.

## 4. Input Identity

- Development Gold: `5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0`
- Execution Manifest: `ef08e5c262d9fc885ab38d81c90f10ce4be6820c31d931c03f0ecdcfe71a534e`
- Snapshot: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Artifact Manifest: `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`
- Eval Protocol: `01f1dd8d6f26bd68962ccb42b489f5be3d086cef2ed0fe90616cb9d3e43db90f`
- Isolation Contract: `faeccb772dd624775e58b55e8614af836fb64d102e7762244b3869767641f18e`

## 5. Held-out Isolation

CandidateSets and deterministic predictions were frozen before Development Gold was opened. Builder and selector interfaces receive no Gold. Case correlation IDs are never serialized to the prompt. Held-out files and protected full-Gold/Human-review families were not opened, parsed, hashed, imported, or searched. Guard violations: 0. Formal Held-out run: false.

## 6. Stage 3A Baseline

Track B baseline was 3/4 complete cases, 6/7 required spans, and deterministic 1/4 hits. Conditional deterministic hit was 1/3. Track A frozen upstream misses for CASE_003/005 were preserved.

## 7. Candidate Robustness Goal

Test whether bounded, Gold-blind, one-substitution matching for short technical acronyms can recover a Candidate miss caused by a single ASR character substitution without dictionaries, Case/video IDs, target spans, or retrieval changes.

## 8. Generic ASR Acronym Policy

Policy `v3.5-stage3b-asr-acronym-anchor-v1` compacts Latin/alphanumeric tokens, removes `.`, `_`, and `-`, matches case-insensitively, accepts uppercase query acronyms of length 2–8, and permits only equal-length substitution distance 1. Non-acronym query words do not expand. The existing 32-Candidate, 6,000-character, 600-second, run/source boundaries remain authoritative. No correction dictionary exists.

## 9. Candidate Robustness Experiments

The bounded maximum was used: Stage 3A baseline plus weights 2.5 and 3.5. All three produced 3/4 complete cases and 6/7 spans; deterministic hits stayed 1. CASE_001/002/005 did not regress. The selected 3.5 configuration is the frozen negative robustness result; no further Builder tuning occurred.

## 10. Final Candidate Builder Configuration

`stage3b-acronym-w3.5-v1`, policy `v3.5-stage3b-asr-acronym-anchor-v1`, 32 Candidates maximum, 6,000 Candidate characters, 500 characters / 60 seconds / six segments per Candidate, 600 seconds union maximum. Evidence Candidate schema remains `v3.5-evidence-candidate-v1`.

## 11. Track A Candidate Results

CASE_001 and CASE_002 remained complete and selector-eligible. CASE_003 and CASE_005 remained typed `upstream_retrieval_failure`; no Oracle substitution was used. A uniform global top-32 cap was frozen before Gold access for the final selector comparison.

## 12. Track B Candidate Builder Results

CASE_001, CASE_002, and CASE_005 were complete. CASE_003 remained incomplete. Aggregate: 3/4 cases, 6/7 spans. Candidate counts were 32, 32, 32, and 14; character totals were 2,908, 2,728, 3,038, and 2,945 respectively.

## 13. Structured Selector Contract

Contract `v3.5-structured-fine-selector-v1` permits only `select` or `abstain`, existing unique Candidate IDs, roles `primary|complementary|context`, and four enumerated abstain reasons. Pydantic strict models and emitted JSON Schema set `additionalProperties: false`.

## 14. Prompt Contract

Prompt `v3.5-structured-fine-selector-prompt-v1` supplies Original Query and stable Candidate serialization only. It forbids answering, summarizing, new evidence, quotes, timestamps, labels, tools, and outside search. No Case ID is present.

## 15. Provider Integration

The existing application-level `OpenAICompatibleProvider` was reused as one instance with configured `deepseek-v4-pro`, high thinking, fixed 120-second timeout, and redacted Keychain credential. No parallel HTTP client was created. Pricing was not guessed.

## 16. Structured Output Validation

Validation rejects malformed JSON, unknown/extra fields, wrong schema/action/role/reason, empty select, non-empty abstain, duplicate/unknown/cross-video IDs, invalid role references, and selection above six. Invalid output is never accepted silently.

## 17. Repair Policy

At most one repair repeats the identical Query, CandidateSet, and ordering with only a short schema error. Config A exhausted all three attempted Track B repairs. Config B required repair for every valid call; two of five still exhausted repair. Final invalid-after-repair rate was 40%, exceeding the 25% stop threshold.

## 18. Candidate Pool Serialization

Fields are Candidate ID, rank, Raw-derived text/start/end, language/type, generation method, and parent rank. Config A revealed Track A pools above the global 32 limit. Config B uniformly froze top 32 before Gold access; Track B remained naturally bounded. No per-Case pool size was used.

## 19. Deterministic Bundle Reconstruction

The LLM returns IDs only. Local code resolves immutable Candidates, enforces one video, sorts by start/end/ID, restores Raw-derived spans/text/time, computes interval-union duration, generates a stable Bundle ID, and validates `v3.5-evidence-bundle-v1` references.

## 20. Track A Selector Results

Eligible: 2. Deterministic: 1/2. Structured: 0/2. Delta: -1. Both structured outputs became valid only after repair, both selected six Candidates, neither abstained, and neither hit. Median union duration: 102.535 seconds.

## 21. Track B Selector Comparison

Eligible: 3. Deterministic: 1/3. Structured: 0/3. Delta: -1. Valid after repair: 1/3; repair exhausted: 2/3. The only valid Bundle selected six Candidates, lasted 105.88 seconds, and missed.

## 22. Per-case Results

| Case | Track A | Track B |
|---|---|---|
| CASE_001 | deterministic hit; LLM valid-after-repair miss | deterministic hit; LLM valid-after-repair miss |
| CASE_002 | deterministic miss; LLM valid-after-repair miss | deterministic miss; LLM repair exhausted |
| CASE_003 | frozen upstream miss, ineligible | Builder miss, ineligible |
| CASE_005 | frozen upstream miss, ineligible | deterministic miss; LLM repair exhausted |

## 23. CASE_001 Regression

The deterministic success was preserved on final CandidateSets. Structured LLM regressed it in both tracks, selecting six overlong Candidates and missing the required group.

## 24. CASE_002 Analysis

The CandidateSet contained complete evidence. Deterministic remained a miss. Track A LLM produced a valid six-Candidate, 96.89-second Bundle only after repair and missed; Track B emitted no valid output after repair. No gain occurred.

## 25. CASE_003 Analysis

The generic matcher detected one-substitution acronym anchors, but ranking alone did not guarantee complete boundary coverage in the bounded pool. Track B remained `candidate_generation_failure`; Track A remained `upstream_retrieval_failure`. The selector was correctly not scored.

## 26. CASE_005 Analysis

All four required spans were present among 14 Candidates. Both Config B attempts failed schema validation, so no complementary Bundle was reconstructed. The deterministic selector also missed.

## 27. Structured Output Reliability

Config B initial-valid rate: 0/5. Valid after repair: 3/5. Repair exhausted: 2/5. Repair rate among valid calls: 100%. Abstention: 0. This violates the reliability stop threshold and blocks recommendation.

## 28. Latency / Token / Cost Signals

Final logical latencies were 116.56–192.65 seconds; median 153.26 seconds and total 782.44 seconds. Provider usage for the three valid responses totaled 16,301 input, 14,338 output, and 30,639 total tokens, including 12,296 reasoning tokens. Failed-call usage and monetary cost are unavailable.

## 29. Bundle Duration and Candidate Budget

Valid outputs always selected the maximum six Candidates. Track A union durations were 108.18 and 96.89 seconds; Track B was 105.88 seconds. Duration ratios were 9.23, 1.52, and 9.03 respectively. Candidate pools never exceeded 32 / 6,000 after Config B freeze.

## 30. Failure Attribution

Builder: CASE_003 Track B. Upstream: CASE_003/005 Track A. Structured selector: CASE_001/002 valid misses plus CASE_002/005 Track B repair exhaustion. No Raw authority, source boundary, Gold leakage, or retrieval mutation failure occurred.

## 31. Tuning History

Builder used exactly baseline + two generic configurations. Selector used exactly two configurations and two pool strategies. Cumulative budget was exactly 10 logical calls and 16 raw attempts. Config B was the final and last call configuration.

## 32. Functional Examples

Generic compaction/substitution, CASE regressions/comparisons, invalid fixtures, repair, and deterministic reconstruction are documented in `research/v3_5/stage3b/functional_examples.md` and the trace assets.

## 33. Trace

Eight Track A/B traces record correlation/query identity, policy and CandidateSet identities, budgets/order, selector versions/model, validation/repair, selected IDs, reconstructed Bundle identity, Raw normalization, and Gold result only after prediction. Request/response hashes are present for valid results and explicitly unavailable for typed failures because failed raw responses were not persisted. API keys and reasoning content are absent.

## 34. Tests and Regression

Directed Stage 3A/3B tests: **43 passed**. Mandated isolation-safe repository regression: **588 passed**, with one Starlette and six multiprocessing deprecation warnings only. Fake Provider tests cover valid, malformed, schema, unknown/duplicate, timeout/failure, repair success/exhaustion, abstain, count limit, prompt isolation, and reconstruction.

## 35. Snapshot / V3 / Gold / Manifest Integrity

All required hashes matched again after implementation. Frozen Stage 3A contracts/configs, Development Gold, Execution Manifest, Snapshot, Artifact Manifest, Eval Protocol, and Isolation Contract were unchanged. No V3 Search was run or retuned.

## 36. Current State Update

`V3_5_CURRENT_STATE.md` records Stage 3A closed, Stage 3B completed as a reliability blocker, all versions/metrics, deterministic preference, false Held-out access, no Sufficiency/Held-out work, time estimate, and active risks.

## 37. Known Limitations

Four Development evidence cases cannot support generalization. Acronym similarity can find anchors but does not itself guarantee complete neighboring coverage. Provider failures lack usage. Schema error payloads were recorded without raw reasoning/output content, so precise model formatting tendencies and failed response hashes cannot be retrospectively recovered beyond typed errors. Cost is unavailable.

## 38. Preferred Selector Decision

`preferred_selector: deterministic`. It preserves CASE_001, has higher Development hits, requires no Provider/repair, and is far cheaper/faster. This is a V3.5 Development preference, not a generalization claim. Structured LLM remains an evaluated negative candidate, not the fallback.

## 39. Stage 4 Recommendation

Stage 4 may proceed only as a separately authorized session using the deterministic EvidenceBundle (or selector abstain when applicable) plus Query. Stage 4 must not redo retrieval, generation, or fine selection. No Sufficiency Judge was implemented here.

## 40. Exact Commands

Repository preflight used the seven mandated Git commands. Hash checks used `shasum -a 256` on authorized assets. Directed tests used:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_v3_5_stage3b_selector.py tests/test_v3_5_evidence_stage3a.py \
  tests/test_v3_5_stage3a_reachability.py
```

Regression used:

```bash
PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  --ignore=tests/test_evidence_snapshot_regression.py \
  --ignore=tests/test_v3_5_eval_stage2a.py \
  --ignore=tests/test_v3_5_eval_stage2b_intake.py \
  --ignore=tests/test_v3_5_eval_stage2b_round2.py \
  --ignore=tests/test_v3_5_eval_stage2c.py \
  --ignore=tests/test_v3_5_stage3a_input_projection.py
```

Development runs invoked `run_stage3b_development(...)` against the locked manifest, Development Gold, artifact manifest, and read-only Snapshot with the configured provider.

## 41. Stop Statement

Stage 3B stopped after the bounded robustness attempt, two allowed selector configurations, 10 logical / 16 raw calls, the >25% invalid-after-repair trigger, artifacts, tests, integrity verification, current state, and this report. Stage 4, Sufficiency, Formal Held-out Eval, API/UI, Agent, Memory, Harness, Translation, and V4 were not started.

Shiliu V3.5 Stage 3B is complete.

A bounded, generic Candidate Builder robustness improvement was evaluated without case-specific or Gold-guided rules. The Structured LLM Fine Selector selected only existing Candidate IDs or abstained under a strict validated schema. All EvidenceBundle text and timestamps were reconstructed deterministically from normalized Raw Subtitle Candidates.

Track A preserved upstream V3 retrieval failures. Track B compared the Structured LLM Selector against the frozen deterministic baseline using Development data only. Held-out labels, Aspects, Evidence Groups, spans and reason codes were not loaded or used.

No Sufficiency Judge, Final Answer, Formal Held-out Eval, API/UI, Agent, Memory, Harness, Translation Pipeline or V4 work was started.
