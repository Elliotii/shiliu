# Shiliu V5.5 Final Gate — Blocked Report

> Date: 2026-08-13  
> Branch: `codex/v5-5-productization`  
> Final Gate baseline: `ec5d685ac1512ff2270b404ae4bcc52f674c351b`  
> Local bounded-correction checkpoint: `a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`  
> Status: **BLOCKED / ROLLED_BACK / NOT_ACCEPTED**

## 1. Decision

The V5.5 Final Gate did not complete because the formal Web `18520` cutover
failed at the launchd reload boundary. The pre-cutover runtime configuration
was restored and the previous formal service was confirmed healthy.

This report is not `V5_5_FINAL_CLOSEOUT.md`, does not declare V5.5 accepted or
closed, and does not authorize a final freeze or push.

## 2. Baseline preflight

- Existing worktree:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu-v5-5-productization`
- Branch: `codex/v5-5-productization`
- Initial HEAD: `ec5d685ac1512ff2270b404ae4bcc52f674c351b`
- G1, G2 and G3 ancestry: confirmed.
- Initial worktree: clean.
- `origin/codex/v5-5-productization` matched the Final Gate baseline.
- G1/G2/G3 Closeouts were present.
- Live DB: `/Users/elliot/Library/Application Support/Shiliu/shiliu.db`.
- DB `quick_check`: `ok`.
- DB foreign-key violations: `0`.

The Charter's functional scope matched Goal 3, but its governance header still
described Goal 2 complete / Goal 3 next. The authorized PASS-only Charter state
update was not performed because the Final Gate did not pass.

## 3. Deterministic verification

Canonical no-provider command:

```bash
env \
  -u OPENAI_API_KEY \
  -u DEEPSEEK_API_KEY \
  -u DASHSCOPE_API_KEY \
  -u NO_PROXY -u no_proxy \
  -u ALL_PROXY -u all_proxy \
  -u HTTP_PROXY -u http_proxy \
  -u HTTPS_PROXY -u https_proxy \
  PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring \
  PYTHONPATH=src \
  /Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python -m pytest
```

### First full-suite run

- `1829 passed`
- `3 failed`
- `4 deselected`
- `7 warnings`

All failures were in
`tests/test_v5_d_r1_e1_runtime_envelope.py`. G1 had placed the durable
task-policy read before the pre-existing pure parameter-envelope validation,
preventing the historical mechanical boundary test from reaching its intended
no-dispatch boundary.

### Sole bounded correction

- Restored pure Gate-B envelope validation before the durable task-policy read.
- Kept durable task authority enforcement before receipt creation, Provider
  factory use or dispatch.
- Updated the accepted-envelope test fixture to provide an explicitly
  Provider-authorized durable task projection.
- Affected tests: `3 passed`.
- Local checkpoint:
  `a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`.

### Final full-suite certification

- `1832 passed`
- `0 failed`
- `4 deselected`
- `7 warnings`
- Duration: `158.80s`

Warnings were one existing Starlette/httpx deprecation warning and six Python
`multiprocessing` fork deprecation warnings.

Additional checks:

- JavaScript tests: `4 passed`.
- All `src/shiliu/static/*.js` syntax checks: passed.
- Python `compileall` for `src` and `tests`: passed.
- `git diff --check`: passed.

## 4. Truth-contract and real-product smokes

Provider calls during Final Gate: `0`.

### Smoke 1 — Research truth and result

PASS on candidate service `18521` using existing task
`rtask_c9a09e60bcab6ffb30bc29baa226bae4`:

- task reopened successfully;
- grounded result and eight current Citation/Evidence entries were visible;
- raw transcript drilldown worked;
- Provider answer and Citation did not upgrade the natural-language objective
  to verified completion;
- the product hierarchy remained question/status/result/evidence/knowledge/next
  step with diagnostics behind Advanced;
- historical blocked task
  `rtask_13f7b3b151e176677f6c79a6d44a58a6` remained visibly paused and was not
  projected as success.

### Smoke 2 — Knowledge rediscovery and reuse

PASS from `/knowledge`:

- the G2 published Topic Page was discoverable without a Research Task ID;
- three facts, currentness and raw transcript links were visible;
- Knowledge remained a read projection over original Evidence, not Citation
  Authority;
- the existing related-query ArtifactRoute / Direct Reuse remained visible.

### Smoke 3 — Whole-product handoff

PASS:

- Library exposed user-language contextual Search and Ask actions;
- Search preserved the query and `folder_id=51947699` scope;
- Search results exposed the user-triggered Research handoff;
- Research received a prefilled objective but remained at the explicit
  `开始研究` submit button;
- no Research task or Provider dispatch was triggered;
- Current Focus `Agent Skill` remained visible on the Research product surface.

## 5. Pre-cutover runtime and rollback point

### Web `18520`

- LaunchAgent: `app.shiliu.web`.
- Executable runtime:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/shiliu serve`.
- Working directory:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Effective code target before cutover:
  `/Users/elliot/.codex/worktrees/post-v5-bounded-repair/Shiliu/src`.
- Effective code HEAD: `f0c704db88f79794c52b3f4f6e6ac77c320470f2`.
- Port: `18520`.
- DB: unchanged live DB listed above.

### Scheduled sync

- LaunchAgent: `app.shiliu.sync`.
- Executable:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python3.12`.
- Command: `-m shiliu sync --scheduled`.
- Effective product-code target before cutover:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu`.
- Code HEAD: `5f1bf4dd899e97583a234b224e209f8c6aac9294`.
- Schedule: every `3600` seconds.
- DB target: unchanged live DB.

Rollback copies:

- `/Users/elliot/Library/LaunchAgents/app.shiliu.web.plist.pre-v5-5-final-gate-20260813`
- `/Users/elliot/Library/LaunchAgents/app.shiliu.sync.plist.pre-v5-5-final-gate-20260813`

## 6. Cutover failure and rollback

The candidate plist edits only changed the Web and scheduled-sync code targets
to the V5.5 worktree. Port, schedule, command semantics, DB and Provider config
were unchanged.

During the Web reload:

- the previous `18520` process stopped;
- `launchctl bootstrap` returned `Bootstrap failed: 5: Input/output error`;
- `18520` did not resume listening.

This matched the mandatory rollback condition. No alternate deployment wiring
or further runtime debugging was attempted.

Rollback result:

- both original plist files were restored;
- restored SHA-256 values matched the pre-cutover values;
- old Web `18520` was restarted successfully;
- `/` returned HTTP `200`;
- rollback Web PID at confirmation: `75696`;
- scheduled-sync configuration and cadence were restored unchanged.

## 7. Final state

- Final Gate: **BLOCKED**.
- Formal V5.5 Web cutover: **not completed**.
- Scheduled-sync V5.5 code-target alignment: **not completed**.
- Previous formal service: **restored and healthy at rollback confirmation**.
- `V5_5_FINAL_CLOSEOUT.md`: **not created**.
- Charter final-state update: **not performed**.
- Push: **not performed**.
- V5.5 CLOSED declaration: **not made**.
- Local branch is one checkpoint commit ahead of origin.

