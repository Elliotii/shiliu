# W01 PostgreSQL infrastructure verification

Scope: explicit configuration, pool lifecycle, safe errors, DTOs and startup
validation interface. No formal W02 schema/Alembic revision, business stores,
production data, model/ASR calls or Application wiring. The W00 frozen fixtures
remain evidence of their original source commit; do not regenerate them for W01.

## Actual local baseline (2026-10-23)

- macOS 26.5 / Darwin 25.5.0, arm64; Apple clang 21.0.0.
- Python **3.12.14**, project supports >=3.10; syntax checked as Python 3.10.
- Server **PostgreSQL 18.6**, `server_version_num=180006`, built from
  [official source](https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2).
  SHA256 `555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f`,
  checked against the official `.sha256` file. No container/digest used.
- Extension **vector 0.8.7**, schema **shiliu**, built from
  [official tag v0.8.7](https://github.com/pgvector/pgvector/tree/v0.8.7), commit
  `f37c13f68b57d2c3472b2214fbcff699d6d34876`. Actual version/namespace are read
  and enforced for every new pool connection. No version substitution.
- `uv.lock`: psycopg/psycopg-binary 3.3.6, psycopg-pool 3.3.3, Python pgvector
  adapter 0.5.1. Alembic will be added in W02. Existing locked versions unchanged.

Sources: [PG supported versions](https://www.postgresql.org/support/versioning/),
[pgvector installation](https://github.com/pgvector/pgvector),
[psycopg pool lifecycle](https://www.psycopg.org/psycopg3/docs/advanced/pool.html).
The documentation may describe development releases; dependencies here use the
stable versions actually resolved in uv.lock.

## Private task resources and reproducible setup

All build/data/socket/venv/results/logs are under `/tmp/shiliu-w01-20261023`
(macOS canonical path `/private/tmp/shiliu-w01-20261023`), mode 0700. No files
from this root belong in Git. No system service, Docker volume, daily DB or TCP
listener is used. Unix socket only, numeric port **55483**. No secret is needed:
local trust auth is restricted by the private socket parent; host auth rejects.
This is a local fixture policy, not a production authentication recommendation.

The existing dedicated instance can be started/stopped from repository root:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python scripts/postgres_w01_local.py start
/tmp/shiliu-w01-20261023/venv/bin/python scripts/postgres_w01_local.py status
/tmp/shiliu-w01-20261023/venv/bin/python scripts/postgres_w01_local.py stop
```

`init` refuses an existing data directory/marker. `start/stop/status` require the
exact task marker and reject symlink/private-root violations. `status` exits 3
when the instance is stopped (the normal pg_ctl convention). Retained resources
are for independent review and are stopped at delivery. After review, stop this
instance, verify `instance.json` equals `{"task":"shiliu-w01-20261023","port":55483}`
(whitespace irrelevant), then remove **only** this entire dedicated root if desired.
No global service is installed or enabled.

To recreate after explicit removal, use these source/build steps; prerequisites
are the already available compiler, make, curl, git, uv (no system package install):

```sh
mkdir -p /tmp/shiliu-w01-20261023/build
chmod 700 /tmp/shiliu-w01-20261023
cd /tmp/shiliu-w01-20261023/build
curl -fsSLO https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2
curl -fsSLO https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2.sha256
shasum -a 256 -c postgresql-18.6.tar.bz2.sha256
tar -xjf postgresql-18.6.tar.bz2
./postgresql-18.6/configure --prefix=/tmp/shiliu-w01-20261023/pg --without-icu --without-readline --without-zlib
make -j8
make install
git clone --depth 1 --branch v0.8.7 https://github.com/pgvector/pgvector.git pgvector-0.8.7
cd pgvector-0.8.7
git rev-parse HEAD
make PG_CONFIG=/tmp/shiliu-w01-20261023/pg/bin/pg_config -j8
make PG_CONFIG=/tmp/shiliu-w01-20261023/pg/bin/pg_config install
```

Return to repository root, sync, then run `init` once and `start`:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/shiliu-w01-20261023/venv uv sync --locked --extra test --python 3.12.14
/tmp/shiliu-w01-20261023/venv/bin/python scripts/postgres_w01_local.py init
/tmp/shiliu-w01-20261023/venv/bin/python scripts/postgres_w01_local.py start
```

The bootstrap uses PostgreSQL single-user mode on a fresh task-owned data dir to
create `shiliu_w01_test_control` and the restricted login role, before exposing a
socket. No connection to an unprefixed default or unknown database is needed.

## Test command

From repository root, with no ambient `PG*` variables:

```sh
SHILIU_DATABASE_URL='host=/private/tmp/shiliu-w01-20261023/socket port=55483 dbname=shiliu_w01_test_control user=shiliu_w01_admin' \
SHILIU_ARTIFACT_ROOT=/private/tmp/shiliu-w01-20261023/artifacts \
SHILIU_ENV=test \
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/results.xml
```

The fixture rejects unknown DSNs before connections/DDL/cleanup: exact task
marker, owner-only root/socket, local socket path/port, `shiliu_w01_test_` prefix,
exact admin/runtime roles, environment `test`, explicit separate Artifact root,
no libpq environment redirection or extra conninfo options. It checks server
version/data directory and runtime role flags before creating a random child DB.
Admin creates the extension and minimal probe table; runtime has DML/USAGE only,
no schema/database CREATE, superuser, role creation, replication or bypass RLS.
Each run drops its random child DB, including test-only startup control objects;
only the empty control database remains. A dedicated test stops/restarts this
marker-verified task instance; do not run parallel suites on this one instance.

Without this PG environment, pure unit/guard tests remain runnable explicitly:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres/test_config_dto.py tests/postgres/test_isolation.py
```

PG tests fail closed when configuration is missing; no automatic skip or Mock
substitution. Do **not** load `postgres_migration_offline` for PG tests: W00's
plugin intentionally blocks sockets. The separate legacy-config check uses that
plugin for three pure configuration tests only; its result is not PG evidence.

## Interface and handoff constraints

Create one `PgDatabase(config)` in the application lifecycle, explicitly `open()`
and `close()` (or `with`), inject it into stores. Constructor/import do not connect.
Default pool 1–8, acquisition 5s, lock/statement/idle-in-transaction 3/15/30s.
Tests use smaller explicit settings. Queue length is capped at 32. Single reads
use short read-only transactions; consistent multi-SQL snapshots explicitly use
`transaction(read_only=True, isolation='repeatable read')`. Cross-store calls
pass `conn`, never borrow/commit internally. Session reset clears SQL session
settings, role, temp state, LISTEN/advisory locks and Python transaction options;
prepared statements are disabled to avoid DISCARD/client cache disagreement.

Errors expose category and SQLSTATE only; pool worker connection/configuration
errors are sanitized before logging. Caller non-DB exceptions propagate after
rollback. `replay_pure_db` is explicit opt-in for replayable DB-only work, at most
3 attempts for 40001/40P01, short bounded backoff. It must never wrap model, ASR,
network, file publication or arbitrary caller contexts.

`validate_startup(revision=..., context=...)` requires the explicit root to exist
and be writable/readable, checks fixed PG/vector version/namespace, exact Alembic
revision and default personal ownership. Missing tables fail. W01 tests create
clearly named `w01_test_only` control objects only inside the disposable test DB;
these are not formal migrations or seeds. W02 supplies real revisions/seeds;
W13 wires validation and orderly shutdown into Application. Startup is not yet
wired, old stores still use SQLite, and W01 does not claim full application PG
migration, formal P1 signoff or C01–C05 concurrency acceptance.

DTO timestamp conversion defaults to UTC ISO seconds (`+00:00`), with explicit
`timespec` override when the domain requires precision. Date conversion is ISO;
ID/bool and JSON objects remain native. Top-level SQL NULL versus JSON null needs
a query `IS NULL` flag, as psycopg returns None for both. Nested JSON null, missing
fields, array order and plain JSON-looking strings remain distinct/preserved.

## W02–W04 continuation / P1 review

The authorized continuation added the complete formal schema and synthetic ETL.
Current Alembic head is `0006_research_reuse_scope`; committed 0001–0004 were not rewritten.
See [schema contract](../../migrations/README.md),
[ETL scope and CLI](../../src/shiliu/migration/README.md), and
[aggregate synthetic evidence](../../docs/reports/POSTGRES_P1_SYNTHETIC_EVIDENCE_20261023.json).

The same guarded environment block above now runs the complete P1 suite:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/p1-results.xml
```

Before supervisory repair: **79 passed / 0 failed / 0 skipped**, 30.51s. Pure L0 checks: 24;
PG-fixture/integration checks: 55. The latter include source/CLI negative cases
whose closed synthetic fixture is itself prepared using formal PG constraints.
W01's 36 assertions remain meaningful, with its test-only startup objects confined
to disposable W01 probe databases. W02 uses separate formal schema databases.

C01–C05 use real independent PG connections and two spawned processes; they are
primitive-level evidence, with full domain wiring left for W10/W12. W04 covers
stable range COPY, atomic receipts/rollback, resume/conflicts, explicit terminal
Research cycle import, identity/highwater and historical byte/DTO checks. Its
fixed512 profile is marked synthetic and inactive. Dump/restore uses another
empty database and a separate Artifact root on the same private instance.

W04 resources are retained only below this task root: sources/w04_* (closed
synthetic SQLite and markers), artifacts/w04_*, backups/w04_*.dump, local XML/logs,
venv and build sources. Fixtures have removed all random test databases; only the
empty control DB remains. The service is stopped at delivery, no system service
is installed. Reuse the existing start/stop commands above; after independent
review, confirm marker/ownership and stopped status before removing only the
whole task-owned root. No W05 or production operation was performed.

All PG clients explicitly disable libpq's default password-file lookup with an
impossible child path of the null device; no personal password file is inspected.
Pool creation/connection also rejects ambient nonempty PG* variables. Dump/restore
subprocesses receive the same disabled PGPASSFILE in their isolated child env.

## W03 supervisory repair

The prior 79 passing tests missed nested tool-budget fences and incorrectly
asserted that replay actions were a tool-call list. The repair keeps thread/run
locks, checks nested final_dispatched and a zoned deadline against actual database
time, and projects the current Run control actions from insertion_seq and native
working_state recovery counters. Old SQLite stores and DDL/ETL are unchanged.

After the repair: **112 passed / 0 failed / 0 skipped**, 48.37s; L0 24,
PG-fixture/integration 88. Final coordination suite: **44 passed**, 24.84s.
Use the guarded environment above and the same pytest commands, with XML paths
`/tmp/shiliu-w01-20261023/w03-repairs-targeted-final.xml` for test_coordination.py
and `/tmp/shiliu-w01-20261023/w03-repairs-p1.xml` for tests/postgres.
This is author verification awaiting independent supervisory review; W05 remains
unstarted. The task instance is stopped, random databases/pool clients removed,
and reproducible resources retained under the existing private task root.

## W05–W07 / P2 author verification

The sections above are chronological P1 records. The current migration head is
`0007_collection_profiles`, mapping `schema26-to-pg-v5`; revisions 0001–0006 and
the frozen W00 fixtures have not been rewritten. P2 covers explicit PG Collection
composition, Taxonomy repositories, immutable Artifact publication/GC, shared PG
FTS, exact512 pgvector profiles, durable projection workers and F1/evidence wiring.
Global Application/CLI and the remaining domain stores are still later packages.

Final combined run: **175 passed, 0 failed/errors/skipped, 89.81s**: original P1
112, P2 61 (W05 35, W06 9, W07 17), plus two original pure chunk tests. From the
repository root, start the dedicated instance with the guarded command above,
export the same explicit test DSN/Artifact root/SHILIU_ENV, then run:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres \
  tests/test_retrieval.py::test_chunking_is_deterministic_preserves_segments_and_overlap \
  tests/test_retrieval.py::test_chunking_honors_duration_and_keeps_oversized_whole_segment \
  --tb=short --junitxml=/tmp/shiliu-w01-20261023/p2-final.xml
```

C06/C07/C08 use real PG and synthetic filesystem objects. The Collection tests
compose stores/services explicitly, with synthetic upstream/ASR/answer providers
and fixed 512-dimensional unit vectors. They do not construct default Application
or assert full Ask HTTP/history/NDJSON, Assistant, Memory, Wiki or Research wiring.
Per-case `tmp_path` directories contain synthetic Artifacts only; migration ETL
resources, XML, scans, build output and audits remain in the private task root.

The already installed pinned Qwen model is an additional opt-in run, excluded
from normal model-free discovery. The separate venv uses the existing lock's
qwen/test extras. With the same guarded database variables:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/tmp/shiliu-w01-20261023/p2-qwen-venv/bin/python -m pytest \
  tests/postgres/local_qwen_cases.py --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/w07-qwen-final.xml
```

This run passed **one test containing eight Chinese cases**, 10.63s; actual model
work measured 9.165s, MPS, one model load, no download/online call. Five semantic
targets ranked first in six synthetic documents (asserted Top3); the other cases
cover short navigation, title and scope/Citation/invalidation/restore. This does
not establish full-corpus quality or a performance improvement.

See [P2 machine evidence](../../docs/reports/POSTGRES_P2_SYNTHETIC_EVIDENCE_20261023.json)
and [append-only execution record](../../docs/reports/POSTGRES_MIGRATION_EXECUTION_20261023.md)
for commits, command results, failure attribution, changed-file coverage hashes,
pending stores and package/wheel checks. No W08 work, push or deployment occurred.
After the final run, random databases and pool clients were zero, control user
tables zero; the dedicated service was stopped (`pg_ctl` status exit 3).

## P2 supervisory lease repair

The original 175 passing tests did not cover expiry while waiting for an
unchanged row lock. The repair adds `test_lease_lock_wait.py`: independent
connections, observed PG Lock waits, fresh SQL clock checks before unlocking,
full business/task/vector state comparisons and subsequent recovery. Collection
claims/checks and projection heartbeat/publish/failure now lock the resource
first, then evaluate time in a separate SQL statement. Recovery uses SKIP LOCKED
and a fresh decision after taking each candidate lock.

New targeted suite: **28 passed**, 53.564s. With the same guarded variables and
dedicated instance, run:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest \
  tests/postgres/test_lease_lock_wait.py --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/p2-lease-targeted-final.xml
```

The combined command above (all tests/postgres plus two original pure chunk
tests) now passes **203 tests, 0 failures/errors/skips**, 143.45s. Use XML path
`/tmp/shiliu-w01-20261023/p2-lease-combined.xml` to preserve the original P2 result.
Before the fix, 17 of the first 19 new cases failed; a separately reproduced sync
audit recovery race also failed. These earlier green runs do not establish the
missing lease contract. Production timeouts and lease defaults remain unchanged.

Qwen was not rerun for this coordination-only repair. The independent supervisor
run at 57013a4 passed one test in 10.685s; this repair leaves model encoding,
recall/profile, chunking and Artifact protocols untouched. P1 scheduler/Research
primitives with a similar static pattern are listed for separately scoped review
and are not claimed fixed. See [repair evidence](../../docs/reports/POSTGRES_P2_LEASE_REPAIR_EVIDENCE_20261023.json)
and the append-only execution record. The task PG is again stopped and only the
empty control database remains. Author repair/self-check is complete; independent
supervisory acceptance remains pending. Stop before W08.

## P3 author implementation: W08 Memory and W09 Wiki

The preceding P1/P2 entries are historical results. P3 starts from `4f1a465` and
stops before W10. Current formal head remains `0007_collection_profiles`, mapping
`schema26-to-pg-v5`; this package introduces no schema revision or fixture rewrite.

Memory uses native PG facts/change/suppression/receipt state, the five recall
channels and exact512 vectors. `MemoryJobWorker` consumes existing assistant_jobs
for index/purge, while `MemoryExtractionWorker` consumes actual memory_extract
Jobs with the shared lane and dispatch budget. Extraction keeps the existing
personal-candidate, quote, retraction, time and scope policies. It stages the
model response before an atomic fact/receipt/FTS/downstream-Job/completion write.
Expired extraction recovery preserves staged proposals and blocks dispatched
unknown results. Models and document encoding execute outside SQL transactions.

Wiki retains source cards/batches, discussion, page/block history, plans,
partial/unknown recovery, merge/revert, tombstone/archive and personal dependency
contracts. `WikiMaintenanceWorker` is a P3-only source_reconcile/extract/integrate
consumer. `WikiHybridIndex(provider, wiki=wiki).search(query, space_id=...,
thread_id=..., task_scope=...)` computes authorized effective windows and queues
missing vectors; callers cannot supply page text as authorization. A historical
relevant Read can additionally restrict page_id. `WikiProjectionWorker` consumes
bounded per-page retrieval_projection_tasks, rechecks dependency hashes and
leases after locking, and atomically publishes windows/vectors/completion.
Failed projections require explicit `requeue_failed(resource_key)` after bounded
retries. Cached construction snapshots support purge, never authorization.

`PgAssistantAccess` supplies only P3's real scoped Space/thread/task/message/Job
edges. It is not the complete W10 Assistant Store. Runtime construction/start
fails closed with an incomplete Store; default Application/HTTP/CLI lifecycle,
full Assistant restoration, Research ownership and global background scheduling
remain later packages. Mem0/FastEmbed/Qdrant/ONNX packages and the Memory backend
lifecycle are retired; the old memory initializer returns a clear retired result.
The base lock now declares NumPy directly for vector validation and optional
Qwen, without Python full-library vector sorting.

With the exact guarded DSN, Artifact root and environment shown above, the final
combined author command is:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres \
  tests/test_retrieval.py::test_chunking_is_deterministic_preserves_segments_and_overlap \
  tests/test_retrieval.py::test_chunking_honors_duration_and_keeps_oversized_whole_segment \
  --tb=short --junitxml=/tmp/shiliu-w01-20261023/p3-combined-author-final.xml
```

This includes the original 203 tests, the Job/lane lock-wait regression,
Memory/actual extraction and recovery, Wiki business/maintenance and effective
window/C10 cases, plus pure import/retirement checks. Fixed vector/structured
model stubs cover contracts, not real semantic quality. The already installed,
pinned Qwen receives a separate strictly offline opt-in run (no new weights):

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/tmp/shiliu-w01-20261023/p2-qwen-venv/bin/python -m pytest \
  tests/postgres/local_qwen_p3_cases.py --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/p3-qwen-author-final.xml
```

That file contains fourteen internal synthetic scenarios across the two domains,
reported as one pytest item. It writes `p3-qwen-author-final-cases.json` under the
private task root, preserving P2 and earlier P3 evidence. It does not establish
whole-library quality or speed. Final counts, source hashes, package checks,
resource audit and the author/supervisor distinction are in the
[P3 completion report](../../docs/reports/POSTGRES_P3_COMPLETION_REPORT_20261023.md)
and [P3 machine evidence](../../docs/reports/POSTGRES_P3_SYNTHETIC_EVIDENCE_20261023.json).
The dedicated PG must be stopped after the sequential runs; no parallel suites
against this one instance. No default Application, production data, paid model,
new model download, push or deployment belongs to this phase.

Final author result at implementation commit `4014110`: **300 passed,
0 failures/errors/skips, 246.992s**. XML identities preserve all original 203;
97 unique P3 additions are 27 Memory, 14 extraction/recovery, 3 composition,
17 scheduler, 13 Wiki business and 23 Wiki retrieval cases. Separate offline
Qwen: **1 passed, 11.524s**, fourteen internal cases, measured model work 10.486s,
MPS, one load. Clean wheel: thirteen installed modules and seventeen migration
resources verified. Final audit: random DBs/user tables/pool clients/other clients
all zero; guarded PG stop returned 0 and status returned 3. Author completion
only; independent supervisory acceptance is pending. Stop before W10.

## P3 narrow-review repairs (2026-10-24)

The original 300 tests and fourteen offline semantic scenarios are historical
checks. Four additional supervisory probes failed, so that initial P3 delivery
was not accepted. The repair is restricted to W08–W09 and still stops before W10.

- Wiki internal Memory calls propagate the already verified principal. The second
  personal owner's successful operations, dependencies, suppression and vectors
  are tested as well as cross-workspace rejection.
- Window build snapshots include verified authored message provenance. A genuine
  forget/purge cleans owned message-derived text and cascading vectors according
  to original suppression scope, including historical blocks/links already
  rewritten. Narrow undo adds no message suppression. Snapshots remain a cleanup
  index, never authorization; original chat/offline backups are not erased.
- Projection claims admit only pending requests for the worker's profile. Bounded
  per-request states and attempts retain other profiles/scopes across partial
  completion, generation changes and failures. An unrelated query does not reset
  a failed request. `requeue_failed` remains explicit.
- All four standalone P3 consumers renew during work with independent short SQL
  connections, default lease 120 seconds / interval 40 seconds. Both Job and lane
  renewal use the same lease transition; projection uses its task protocol. The
  lifetime helper joins its thread on every exit. Renewal failure stops renewal
  and publication, while real lock-time owner/epoch/lease/version checks remain.
  Constructor-only `lease_seconds` and `heartbeat_interval` allow bounded real
  PG tests; intervals greater than one third are rejected, defaults unchanged.

With the same guarded DSN/Artifact root/SHILIU_ENV, run all existing tests and
repair cases sequentially on the dedicated instance:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres \
  tests/test_retrieval.py::test_chunking_is_deterministic_preserves_segments_and_overlap \
  tests/test_retrieval.py::test_chunking_honors_duration_and_keeps_oversized_whole_segment \
  --tb=short --junitxml=/tmp/shiliu-w01-20261023/p3-repair-combined-final.xml
```

`test_p3_repairs.py` retains expected supervisor contracts. `test_p3_renewal.py`
uses real PG with explicit short leases and tests long work and actual owner-loss
for index/purge, extraction, source maintenance and window projection; it also
checks recovery, unknown non-replay and absence of heartbeat threads/idle SQL
transactions. Separately, the default-lease acceptance waits a real 121 seconds
inside a purely local model stub, without modifying DB expiry or default claim:

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest \
  tests/postgres/local_p3_renewal_case.py --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/p3-repair-default-renewal.xml
```

This opt-in slow case writes `p3-repair-default-renewal.json` under the private
task root. It preserves the supervisor's failing probe and the previous author
results. Final repair counts/hashes, a separately named offline Qwen rerun,
package checks and resource cleanup are recorded in the updated completion
report and independent repair machine evidence. Author repair self-check is
separate from the still-required independent narrow revalidation.

The repair's offline Qwen rerun uses the original fourteen-case source copied
under `/tmp/shiliu-w01-20261023/test_p3_repair_qwen.py`, with only the result
filename changed to `p3-repair-qwen-cases.json` and the same guarded collection_db
fixture imported for standalone execution. Preserve previous author/supervisor
JSON bytes. With the same three explicit database/Artifact/test variables:

```sh
PYTHONPATH=/absolute/operator/new-systems/agent-job-prep/Shiiu-1023/tests/postgres:/absolute/operator/new-systems/agent-job-prep/Shiiu-1023/src \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/tmp/shiliu-w01-20261023/p2-qwen-venv/bin/python -m pytest \
  /tmp/shiliu-w01-20261023/test_p3_repair_qwen.py --tb=short \
  --junitxml=/tmp/shiliu-w01-20261023/p3-repair-qwen.xml
```

Final repair result at `aec1299`: **326 passed, 0 failures/errors/skips,
307.444s**. All original 203/300 testcase identities are retained; the 26 unique
new cases are sixteen repair contracts plus ten bounded renewal cases. A
separate default120/real121-second acceptance passed in 122.877s with three
observed renewals and one model call. The separate offline Qwen rerun passed one
item/fourteen scenarios in 11.425s (model work 10.269s, MPS, one load). Failed
intermediate probes and the read-observer race remain separate evidence; no
counts are added across rounds. Final audit found zero random DBs, control user
tables, pool clients and other clients. Guarded stop returned0/status3. Updated
completion report and `POSTGRES_P3_REPAIR_EVIDENCE_20261024.json` state author
repair/self-check completion and independent narrow revalidation pending.

## P4 author verification (2026-10-24)

Current formal runtime is PostgreSQL only. Application validates explicit
SHILIU_DATABASE_URL, independent SHILIU_ARTIFACT_ROOT and SHILIU_ENV before
consulting default paths/credentials, owns one pool and injects trusted context.
Alembic is explicit, never run by Application. Current head is
0011_research_candidate_boundary (schema26-to-pg-v8). Historical sections above
remain evidence of their original source points.

On product source 037b48861534eea359ac0e6fd257381839a1be8a, tests/postgres plus
the two pure tests/test_retrieval.py chunk selectors passed 500/0/0/0 in
462.099s; all 326 original testcase identities retained. Use explicit isolated
configuration and serial suite execution as above. Do not run default daily
Application or historical real-corpus/online test entrypoints.

The explicit optional `local_qwen_p4_cases.py` reuses the installed pinned
Qwen semantic case set but redirects output to p4-qwen-cases.json, preserving
P3 evidence. It is not automatically collected by the baseline file pattern.
Both HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 are required, with the existing
p2-qwen-venv and isolated PG target. No model installation/download is needed.

Full evidence, contract mapping, known unchanged JS-copy assertion failure,
packaging bootstrap limitation and final shutdown audit are in
`docs/reports/POSTGRES_P4_COMPLETION_REPORT_20261024.md` and its machine evidence.
This is author completion, pending independent supervisor acceptance; W14–W16
remain outside this run.

## P5 W14/W15 (2026-10-24)

Current CLI supports complete113-source-table bounded ETL, explicit historical
approval/provenance, ownership, all-file bindings, offline none/Qwen rebuild and
paired independent restoration. See src/shiliu/migration/README.md and
[operations/P6 runbook](../../docs/POSTGRES_OPERATIONS_AND_P6_RUNBOOK.md).
The original W04 fixture and original507 testcase identities remain; full-table,
Stage5 live PG, historical boundary, ASR poll-only, C13 true backend termination
and continuous mixed projection rounds are additional cases. Counts/source point
belong to the final P5 report, not a sum of development reruns.

Run the established full command serially (admin control DSN only for test DB
bootstrap, runtime/ETL roles are derived by guarded helpers):

```sh
python -m pytest tests/postgres \
  tests/test_retrieval.py::test_chunking_is_deterministic_preserves_segments_and_overlap \
  tests/test_retrieval.py::test_chunking_honors_duration_and_keeps_oversized_whole_segment \
  --tb=short --junitxml='<private evidence>/p5-final.xml'
```

`local_qwen_p5_cases.py` is explicit opt-in, never automatic collection. It uses
the installed pinned model with HF_HUB_OFFLINE=1/TRANSFORMERS_OFFLINE=1 and writes
P5-specific files without overwriting P2–P4 evidence. Model-free tests use fakes.
Never run suites concurrently on this dedicated service: C13 stops/restarts the
marker-verified PG after killing an uncommitted ETL backend. Historical targets
are only used under specific approval and never started as Application workers.

### 0012 字幕 BM25 依赖

当前产品池还要求预加载 pg_textsearch 1.5.1（commit
`fa142d049d08eac45a263f5abc250c8877ae076e`）。安装到独立测试程序树，
不要修改已被正式实例共用的 W01 程序树。schema_support/probe bootstrap 显式安装
`shiliu_search` 扩展并授予最小查询权限；缺库不能跳过版本检查。
此次实现的精简验收使用 `SHILIU_BM25_PRODUCT_TEST=1 PYTHONPATH=src:. python -m pytest
 tests/test_collection_bm25_product.py`（一行），绑定新的 55487 私有 runtime，
不要求重跑 W01 历史全套。安装/恢复前置条件见正式 operations runbook 的 0012 节。
