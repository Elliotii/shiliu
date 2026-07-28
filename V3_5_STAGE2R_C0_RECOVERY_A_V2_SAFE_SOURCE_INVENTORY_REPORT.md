# V3.5 Stage 2R-C0 Recovery A v2 — Safe Source Inventory Report

## Completion status

```text
Stage 2R-C0 Recovery A v2 Complete
Safe Development Source Inventory Ready
External Construction Workspace Ready
```

This session is permanently ineligible for case construction, candidate selection, primary or secondary review, human adjudication, judge development, and held-out evaluation. A new, isolated C0 Constructor session may consume only the external workspace. The main session has no remaining inventory/export blocker.

## Frozen authorities

- Frozen DB: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db`
- Frozen DB SHA-256: `61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1`
- Artifact root: `/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts`
- Artifact manifest: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/artifact_manifest.jsonl`
- Artifact manifest SHA-256: `36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f`
- Corpus manifest: `/Users/elliot/new-systems/agent-job-prep/Shiliu/research/v3_eval/corpus_manifest.json`
- Corpus manifest SHA-256: `f93338b796b40e5c95c9025e488195a2a6302e9d4da5960e6496a8dab2fc2a1f`
- Frozen workflow manifest SHA-256 before and after: `d64d72ebd283fb86d798b9c026a230569d924cdcf2c77471b5a5e0b2c72df394`

The corpus manifest's declared snapshot path and SHA-256 match the frozen authority. HEAD was `8287c8d92378b87290274d02605cdc704cb8c470`, exactly as expected. The pre-existing dirty worktree was retained.

## Protected inputs and access controls

The deterministic aggregate-only processor used exactly these five protected inputs:

- `research/v3_eval/eval_queries.locked.jsonl`
- `research/v3_eval/eval_gold.locked.jsonl`
- `research/v3_eval/eval_gold_review.decisions.amended.jsonl`
- `research/v3_eval/gold_lock_audit.json`
- `research/v3_eval/human_ledger_amendment_audit.json`

No repository-wide discovery/search was performed. Quarantine contents were not opened. Stage 3 or Stage 4 contents were not opened. No protected query, excluded source, protected video, label, span, aspect, or record detail was emitted. The processor proved 20 protected query identities and 34 protected video identities in aggregate, excluding 21 enumerated sources. Unknown-protection exclusions: 0; unknown-protection sources included: 0.

## Pilot coverage

All four expected pilot cases were restored deterministically. The validated distribution is sufficient 1, partial 0, insufficient 3, unverifiable 0, total 4. Two distinct safe inventory sources cover the four pilot links. No status was inferred or changed.

## Inventory aggregates

- Frozen source rows enumerated: 144
- Safe inventory sources: 123
- Available: 116
- Unavailable: 7 (all retained as metadata-only missing sources)
- Source type distribution: human 5, AI 108, ASR 4, unknown 6
- Source language distribution: zh 116, en 1, unknown 6
- Single timeline: 115
- Multiple timelines: 1
- No valid timeline because unavailable: 7
- Existing-pilot safe sources: 2
- Candidate cases constructed: 0

## External export and integrity

- Workspace: `/tmp/shiliu-v3-5-c0-construction-input-v2/`
- Workspace outside repository: yes
- Raw source exports: 116
- Raw hash mismatches: 0
- Protected source overlap: 0
- Unknown protection state included: 0
- Repository files copied beyond the explicit inventory/pilot/frozen-workflow allowlist: no
- Forbidden filename violations: 0
- Forbidden generated-key violations: 0
- Secret-scan violations: 0
- Repeated build byte-identical: yes

The frozen workflow manifest is the single explicit content-scan exception because this task requires its byte-identical copy and that authority itself contains legacy workflow terminology. Its filename and SHA-256 remain pinned.

## Output hashes

- Inventory: `190eb819d197838b7e2e7d4da8ba40b9db8b5e05aae5f95bccdc0b28034c0a48`
- Inventory manifest: `acaceba24360aa3cd5c375d4e74c56595ecc0b1b4443daa17fe68cab303a3f69`
- Inventory audit: `f0e06aafab2fb538d0785138eb5811b2e391ea19fe273b3fd6a9e986abc5693a`
- Pilot coverage: `fb81708fdf5236f6e3c7b331d608f47ead4e9fbb726891646a65158d32d5f5d7`
- Workspace manifest: `b7c424fa08256e58ae27071d4eaa5ec57e824a8f5d53585d7b19c27780e88095`

## Model and mutation audit

Reviewer calls: 0. Provider calls: 0. LLM calls: 0. Embedding calls: 0. Gold records created: 0.

Eval v1, Frozen V3, and the frozen reviewer workflow were not modified. The build wrote only the four requested implementation modules, three focused test files, the four requested repository outputs, this report, and the fixed external workspace.
