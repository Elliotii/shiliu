# W14 complete, explicit offline migration

Legacy nonterminal `memory_purge` is completed during typed import only when the
resolved owner matches an already-forgotten Memory whose online text/excerpt are
cleared. Import clears its lexical representation and imports no legacy Memory
vectors. The Job's `migration_completion` payload records the versioned policy
and deterministic input-time anchor (`max(source Job.updated_at,
source Memory.updated_at)`), not a historical worker execution time. Its terminal
lease/error fields are cleared; attempt/lease_epoch and original staging audit
remain intact. Reentry validates the same completion without a worker claim or
event. Active indexing remains migration-pending, including without a model.
The completion disposition binds only affected source manifests; an old receipt
for such an input is rejected, while unaffected historical A bindings stay exact.

`python -m shiliu.migration` implements inspect / plan / import / validate /
rebuild / report without Application, paid job dispatch or a default daily path.
Every action requires source, target DSN, independent Artifact root, environment
and run ID. The target guard is task-local: exact marker/private root, socket,
PG18.6/vector0.8.7, role and shiliu_w01_test_* database. Runtime cannot read
staging. ETL has formal DML, staging CREATE/DML and sequence calibration, no
formal DDL, trigger-disable, superuser or bypass RLS.

Inputs are new private `sources/w04_*` or `sources/w14_*` packages containing
source.sqlite3, files/, artifacts.json, and exactly one synthetic.json or
historical.json. Historical provenance requires actual prior human approval,
explicit ownership.json and a matching database SHA256. A marker is a recorded
precondition, never a substitute for approval. Synthetic fixed vectors are
rejected on historical inputs. Each principal maps explicitly to its own
workspace; unknown owners never merge into local_operator.

The complete frozen Schema26 source/column contract admits only reviewed column
ordering and two observed historical DDL variants. Unknown nonempty data,
invalid JSON/time/bool/number, orphan, unsafe file or source change fails closed.
All113 retained formal source tables are supported; derived FTS/shadow/candidate
objects are explicitly classified. Table counts do not prove natural history
state coverage. The original W04 65-table/83-row semantic fixture remains frozen;
a separate full-table fixture exercises 1105 event rows across nine bounded
batches and all113 source tables.

Stable PK keyset batches (128 rows) stream through COPY staging, typed conversion,
formal insert and batch receipt in one transaction. Immutable self-reference
parents in later ranges are scheduled first. Mutable nullable cycles use two
phases. The terminal Research atomic group includes tasks/goals/attempts/
checkpoints/results AND independent task derivations required by0010; real FKs
and deferred constraint triggers are forced immediate before commit. No fake
status, disabled trigger or NOT VALID FK. IDs/seq/epochs and dedupe keys remain;
sequence/membership highwater is calibrated. Same-ID different payload rejects.

SQL NULL and JSON null differ; arrays retain order, objects canonicalize keys,
time canonicalizes UTC and finite floats retain explicit typed identity. Frozen
JSON and original source bytes are not reserialized. Version-specific file
bindings cover videos, SourceSnapshots, ASR input, Taxonomy output, Research
exports and raw Source Version references. Required bytes and Taxonomy declared
raw/canonical hashes must match; optional expired ASR scratch is separately
classified, without changing status/attempt/upstream identity. Preserve unknown,
not_before, holds, Context and business-day/lane usage. No automatic paid replay.

Run identity binds source hash, mapping version/hash, ETL policy, ownership,
Artifact descriptors, provenance and normalization evidence. A new run requires
a seed-only target. Existing receipts revalidate on resume; ready reentry only
validates. import/validate/rebuild share a bounded administrative advisory lock.
`ready` validates this isolated input, never authorizes cutover.

`rebuild --embedding none` computes current lexical representation and reports
semantic unavailable/missing. `--embedding qwen --model-path <explicit installed
path>` uses only pinned local Qwen identity, offline flags and existing domain
projection policies. It preserves unit identities/content and history, computes
outside transactions, publishes scoped versions and records full derived table
snapshots. Interrupted building receipts block ready; model recovery is explicit.
Task-specific Wiki variants stay on demand. No old Memory BGE import.

## Source planning and approved copying

The read-only audit script accepts explicit source/allowed roots/private output,
refuses open handles, nonempty WAL/journal and symlinks, hashes source before and
after, and prints aggregates only. `python -m shiliu.migration.package plan
--audit <private audit> --private-plan <new private file>` writes locators/hashes
and precise recipes, not document bodies. This step does not copy a database.

Only after specific human approval, `package prepare --plan <approved file>
--destination <new task package> --approval-reference <actual approval>` rechecks
source closure and every allowed file, copies original bytes and creates the
historical marker. The narrowly checked support-policy inverse is a separately
labelled derived representation; observed source bytes and audit remain intact.
Unknown mismatches reject. Schema24/25 normalization uses `python -m
shiliu.migration.normalize --source <guarded package/source.sqlite3>
--destination <new w14 package>`; only the new copy is upgraded by frozen DDL.
Never use these tools to normalize or checkpoint an original candidate.

## Explicit invocation and recovery

```sh
python -m shiliu.migration plan \
  --source '<private task package/source.sqlite3>' \
  --source-manifest '<same package/artifacts.json>' \
  --source-content-root '<same package/files>' \
  --owner-map '<same package/ownership.json>' \
  --database-url '<guarded restricted ETL DSN>' \
  --artifact-root '<independent private task Artifact root>' \
  --environment test --run-id w14_review
```

Use those same explicit parameters for inspect/import/validate/rebuild/report;
inspect/plan make no PG connection, though target configuration is guarded.
Validate/report use read-only PG transactions. `backup.create_pair` requires a
quiescent target and new private directory; it binds a pg_dump hash, all object
hashes and validation. `restore_pair` accepts only another empty database/root,
restores restricted grants and checks the same paired input. Corrupt dump/bytes
reject before restore. Never substitute an existing daily target.

Operational/P6 writer, backup and rollback instructions are in
[the runbook](../../../docs/POSTGRES_OPERATIONS_AND_P6_RUNBOOK.md). W16 is separate.

## W16 exact persistent deployment (2026-10-25)

The optional production guard is bound to the one approved
`Shiliu-Postgres-20261025` resource manifest, local socket/55484, two exact
production/restore database names and their private Artifact roots. It rejects
arbitrary DSNs, ambient libpq overrides, different roles, symlinks and synthetic
production sources. W01 remains on its original private test resources. Source,
target, binary, backup and restore roots must belong to the same binding.
Admin/ETL/runtime are restricted roles; the bootstrap account is NOLOGIN after
schema/vector creation. Admin and ETL can read server settings solely to verify
the actual data directory; they cannot create roles/databases or disable guards.
The restricted restore role uses an independently preinstalled exact vector
extension; only its bootstrap schema/extension/comment TOC entries are reused,
while all data, constraints, triggers and other schema entries restore normally.

`python -m shiliu.migration.detached start` runs only from the fixed installed
production runtime, with explicit source/run/manifest/code/model/attempt. It
creates a separate OS session, empty stdin and ordinary log files, then returns.
The runner waits for the original rebuild CLI and atomically writes exit.json
(and validated result.json), without retry, cutover or background recovery.
Missing exit.json means running or unknown, never success. run.json stores PID
start identities; old PID presence alone is insufficient. Model encoding remains
strictly offline. Optional caffeinate lasts only until this runner exits.
Attempts are independent; the existing target-local reentry remains, but not all
domains promise exact resume without recalculation. No vector reuse across dumps.
