# Shiliu V5.5 Final Closeout

> Date: 2026-08-13  
> Branch: `codex/v5-5-productization`  
> Status: **PASS / ACCEPTED_PENDING_USER_FINAL_FREEZE**

## 1. Version decision

V5.5 Final Gate is **PASS / ACCEPTED_PENDING_USER_FINAL_FREEZE**.

The certified product source is the local bounded-correction checkpoint
`a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`. Operational Recovery changed
only LaunchAgent code-target wiring and reload sequencing; it did not modify
`src/`, `tests/`, the DB schema, product behavior or Provider policy.

## 2. Baselines

- Initial V5.5 baseline:
  `f0c704db88f79794c52b3f4f6e6ac77c320470f2`.
- Goal 1 frozen HEAD:
  `cc707a62f32698d8fc5cbeb36995e0b05736d066`.
- Goal 2 frozen HEAD:
  `09e50bd0f3b4c4a7d86ad90306d766369b4b2572`.
- Goal 3 frozen HEAD / original Final Gate baseline:
  `ec5d685ac1512ff2270b404ae4bcc52f674c351b`.
- Final Gate bounded product-code correction checkpoint:
  `a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`.

The bounded correction restored the established ordering in which pure Gate-B
runtime-envelope parameters are validated before the durable task-policy read.
The durable Provider authority check still runs before receipt creation,
Provider factory use or dispatch.

## 3. Full deterministic verification

Canonical environment:

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

Initial run: `1829 passed / 3 failed / 4 deselected / 7 warnings`. The three
failures shared the single ordering regression described above. After the sole
bounded correction, the affected file passed `3 passed`, and the mandatory
second and final full suite certified:

```text
1832 passed
0 failed
4 deselected
7 warnings
```

Warnings were one existing Starlette/httpx deprecation warning and six Python
`multiprocessing` fork deprecation warnings. JavaScript tests passed `4/4`;
all product JavaScript syntax checks, Python `compileall` and
`git diff --check` passed.

Operational Recovery did not modify product or test code, so it did not rerun
the full suite and reused this certification.

## 4. Truth-contract verification

- **Research:** Provider answers and Citations did not grant
  `objective_verified`; kernel `valid_success` remained distinct from verified
  user completion. Failure, waiting and blocked states retained priority.
  Unknown Provider side effects remained non-replayable, and Branch/Replay
  continued to require explicit durable-effect confirmation.
- **Evidence:** raw subtitle/raw ASR remained Citation Authority. Metadata,
  Knowledge and Personalization remained projections or assistance only.
- **Knowledge:** blocked/incomplete Research could not publish. Successful
  Research did not auto-publish; Review/Publish required explicit confirmation.
  Fact, Artifact and Topic Page retained Evidence lineage, and reuse created no
  new fact authority.
- **Personalization:** Current Focus remained explicit user authority;
  inferred/candidate state did not auto-upgrade. Product handoffs did not become
  an automatic Router, and Search/Ask to Research still required explicit
  submission.

## 5. Final real-product smokes

All three candidate smokes passed without Provider dispatch.

1. **Research truth/result:** existing task
   `rtask_c9a09e60bcab6ffb30bc29baa226bae4` reopened with its grounded result,
   eight current Citation/Evidence entries and raw transcript drilldown. Its
   natural-language objective remained unverified. Historical blocked task
   `rtask_13f7b3b151e176677f6c79a6d44a58a6` remained safely paused rather than
   projected as success.
2. **Knowledge rediscovery/reuse:** `/knowledge` rediscovered the G2 published
   Topic Page without a Task ID, displayed its three facts, currentness and raw
   transcript lineage, and retained the existing ArtifactRoute/Direct Reuse.
3. **Whole-product handoff:** Library to Search/Ask used user language and
   retained the query plus `folder_id=51947699`. Search to Research prefilled
   the objective but stopped at the explicit `开始研究` button. Current Focus
   `Agent Skill` remained visible.

## 6. Provider readiness

Provider dispatch was unnecessary and prohibited during Operational Recovery.
The accepted Goal 1 live Provider proof remained authoritative; G2/G3 and the
Final Gate correction did not change Provider core or runtime policy. Runtime
configuration continued to resolve the registered Provider/model settings.

Provider calls during Final Gate and Operational Recovery: `0`.

## 7. Historical blocked attempt and root cause

The first formal cutover attempt failed with
`launchctl bootstrap` error 5 and correctly rolled back. The immutable history
is recorded in `V5_5_FINAL_GATE_BLOCKED_REPORT.md`.

Operational Recovery found the exact cause in the macOS unified launchd log:

- at `04:27:52.509`, bootstrap was rejected with
  `Operation already in progress`;
- the old Web process did not exit and its registration was not removed until
  `04:27:53.193`.

The first attempt had called bootstrap immediately after bootout, racing the
asynchronous shutdown/removal window by approximately 684 ms. Candidate plist
syntax, paths, permissions, label/domain, executable and Python import were all
valid; there was no candidate process startup failure.

The minimal operational fix was to wait until
`launchctl print gui/501/app.shiliu.web` confirmed the registration was absent
and port `18520` was no longer listening, then perform the single authorized
bootstrap/kickstart. Cutover retry count: `1`.

## 8. Operational cutover

### Web `18520`

- Service label: `app.shiliu.web`.
- Executable:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/shiliu serve`.
- Previous effective source target:
  `/Users/elliot/.codex/worktrees/post-v5-bounded-repair/Shiliu/src` at
  `f0c704db88f79794c52b3f4f6e6ac77c320470f2`.
- Final WorkingDirectory:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu-v5-5-productization`.
- Final `PYTHONPATH`:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu-v5-5-productization/src`.
- Certified product-code checkpoint:
  `a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`.
- Final PID at cutover confirmation: `76370`.
- Port: unchanged at `18520`.
- Status: loaded, running, listening and healthy.

### Scheduled sync

- Service label: `app.shiliu.sync`.
- Executable and command unchanged:
  `/Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python3.12 -m shiliu sync --scheduled`.
- Final WorkingDirectory and `PYTHONPATH`: same V5.5 worktree/source target as
  Web.
- Schedule: unchanged at every `3600` seconds.
- DB target, sync scope, command semantics and retry behavior: unchanged.
- Status: loaded/configured, idle after reload; no full sync was triggered.

### DB and rollback

- DB path remained
  `/Users/elliot/Library/Application Support/Shiliu/shiliu.db`.
- DB `quick_check`: `ok`.
- DB foreign-key violations: `0`.
- Rollback plist copies remain at:
  - `/Users/elliot/Library/LaunchAgents/app.shiliu.web.plist.pre-v5-5-final-gate-20260813`
  - `/Users/elliot/Library/LaunchAgents/app.shiliu.sync.plist.pre-v5-5-final-gate-20260813`

## 9. Formal operational smoke

The certified candidate on formal `18520` returned HTTP `200` for:

- `/`
- `/search`
- `/ask`
- `/research`
- `/knowledge`

Launchd reported the candidate WorkingDirectory and `PYTHONPATH`, Web remained
running with a new PID, scheduled sync retained its 3600-second interval, and
the live DB remained healthy.

## 10. Remaining limitations

- Web still uses FastAPI `BackgroundTasks`; there is no independent Worker or
  automatic cross-process rescheduling.
- Unknown Provider side effects still require explicit resolution and are not
  automatically replayed.
- `/knowledge` remains a bounded recent-50 Topic Page read projection rather
  than a new Knowledge search/index.
- Later-query Direct Reuse still requires explicit user-provided required
  aspects.
- The formal launch wiring continues to use the existing shared virtual
  environment executable while pinning source through the accepted worktree
  `PYTHONPATH`; no dependency or deployment architecture change was authorized.

## 11. Final Gate changes

- Product-code correction: the sole ordering correction at
  `a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`.
- Operational fix: synchronized launchd bootout/bootstrap sequencing and
  minimal Web/Sync WorkingDirectory plus `PYTHONPATH` alignment.
- No schema, DB, Provider policy, schedule or product-behavior changes.

## 12. Final candidate status

`READY_FOR_USER_FINAL_ACCEPTANCE_AND_FREEZE`

The governance/report commit containing this Closeout may have a newer Git SHA,
but the certified product source remains exactly checkpoint
`a8f4e6c08d37468d8a82a0fd7a48bfcf4afb5350`.
