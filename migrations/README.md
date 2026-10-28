# Current release: Schema 0014

Current HEAD is `0014_assistant_source_patch` (132 application-schema tables including Alembic). Revisions 0012/0013/0014 add Collection BM25, the thin message index and source-patch approval constraints. Use the dedicated administrative connection for upgrades; runtime does not migrate. The original frozen source mapping below remains historical ETL evidence; operational 0014 backup instead uses `contracts/runtime_0014_catalog.json`. See [paired backup](../docs/operations/POSTGRES_PAIRED_BACKUP.md). No downgrade-based data rollback is promised.

# PostgreSQL schema contract (W02)

The explicit revision chain is `0001_scope_core` → `0002_agent_domains` →
`0003_retrieval_artifacts` → `0004_backfill_scope` →
`0005_dispatch_input_identity` → `0006_research_reuse_scope`. `shiliu.alembic_version` is the startup contract;
`shiliu.vector` is pgvector 0.8.7 on PostgreSQL 18.6. Revisions are executed only
by an explicit administrative migration connection, never by Application or a
runtime store. `upgrade(conn, revision)` consumes a dedicated connection and owns
its migration commit/close. It is not a cross-store transaction helper.

- `contracts/schema26_target.json` binds the frozen W00 source SHA256 and source
  attributes to explicit target columns, keys, checks, FKs, indexes and triggers.
  Each excluded source object and retired formal column has a reason. A per-column
  source payload makes nullable PK/type/default changes inspectable.
- `sql/0001.sql` through `0006.sql` are reviewed static PostgreSQL DDL; their
  SHA256 values are in the mapping. No runtime SQLite SQL translation, inference,
  ORM entities or autogenerate shortcut is used.
- `contracts/pg18_catalog.json` is actual catalog output from a fresh task-local
  server, after all six revisions applied separately. No business rows, DSNs,
  secrets or private content are included. Tests compare it structurally with the
  expanded mapping. CHECK ASTs are independently parsed in temporary PG tables
  from mapping expressions and compared with the revision definitions.

Source ordinary tables: 118; 113 retained, five explicitly retired/replaced.
Target: 130 tables / 1748 columns / 195 CHECK / 489 FK / 86 preserved source
BEFORE triggers plus two profile and two dispatch binding/receipt immutability triggers. JSON root-reference and
personal-dependency guards are additional. The installed vector extension has
its own objects and is not counted as application tables.

Private roots reference `(workspace_id, principal_id|owner_user_id)` to the
personal workspace owner. All child relationships inherit/pin workspace, and
multi-parent relationships have explicit correlated root keys. Existing actor,
principal, worker owner and lease semantics remain distinct. A new historical
principal must get its own explicit personal workspace mapping; never merge into
local_operator silently. No shared-workspace/authentication implementation is
claimed.

Source rowid ordering has explicit targets: membership_seq for memberships;
insertion_seq for Assistant runs and Research outer audits/continuation decisions/
seeds. ETL imports these values and resets identities. Other source numeric IDs,
seq and epochs retain their types/values. JSONB is not raw Artifact identity;
byte hashes and comprehensive source revision hashes remain separate.

DDL preserves nullable UNIQUE semantics and all source CHECK/partial index
intent. Composite SET NULL actions null only the optional link, not inherited
non-null workspace/root columns. Research full-row versus lineage-only BEFORE
triggers retain their original conditions. The event delta conditional trigger
also keeps its OLD/NEW event-type test. Import never disables triggers or leaves
unvalidated FKs. Downgrade deliberately fails and directs backup restoration.

A management identity installs the extension and Alembic schema. The explicit
`grant_roles` operation grants runtime business DML, sequence usage and revision
SELECT; it denies runtime access to migration ledgers/staging or DDL. The ETL
identity is separate, has business/ledger DML, sequence UPDATE for calibration and staging CREATE, and cannot
change formal schema, disable triggers, create extensions or bypass RLS.
Provision roles separately with no superuser/createdb/createrole/replication/
bypassrls. The local fixture's admin/ETL/runtime policy is not production auth.

Run from repository root with the guarded task environment described in
[tests/postgres/README.md](../tests/postgres/README.md):

```sh
/tmp/shiliu-w01-20261023/venv/bin/python -m pytest tests/postgres/test_schema.py --tb=short
```

The fixture creates only random prefixed databases on the known private task
socket, verifies marker/version/data directory/role flags, upgrades them, and
drops them after verification. Tests cover empty/stepwise upgrade, exact catalog,
source coverage, every source immutability/lineage trigger, legal state updates,
nullable uniqueness and FK/owner/thread/video/Space/task/evidence negatives.

Formal schema presence does not mean product stores have been ported. Domain
SQL, Context installer, recovery and APIs are connected in their later W05–W13
packages. P1b ETL first validates synthetic closure; historical distribution and
production cutover remain outside W02.

The fourth revision was added during W04 closure review to bind metadata holds
to their scoped video and old/new Wiki-intent revisions to the same video. The
first three committed revision SQL files were not rewritten.

The fifth revision binds dispatch input hashes and preserves receipt identity while
allowing status/usage settlement. Legacy NULL hashes are unverifiable, never
invented during ETL. The sixth permits same-workspace cross-task material reuse
for route outcomes and artifact/page facts, while requiring a continuation or
derived task to have the real source parent. Original task-owned roots stay
scoped. Source evidence: knowledge_reuse.py direct reuse, incremental artifact
finalization and child creation; knowledge_service.py topic-page material links.
Already committed revisions 0001–0004 remain byte-for-byte unchanged.

## W07 Collection scope/trace continuation

Current head: `0011_research_candidate_boundary`, mapping `schema26-to-pg-v8`. Revision
0008 adds a `released` dispatch receipt state for reservations proven not to have
been sent; revisions 0001–0007 remain immutable.
0001–0006 remain unchanged. The seventh revision scopes retrieval unit/vector
primary keys to workspace while retaining exact stable string IDs and existing
composite relationships. Four nullable trace provenance columns preserve old
rows as historical NULLs. Current catalog: 130 tables / 1752 columns; CHECK/FK/
trigger counts remain 195/489/95. Empty and seven-step upgrades plus P1 ETL and
restore are tested; product worker/query verification continues in W07.

Revision 0009 retains original read-only ancestor checkpoint branch/replay. Workspace FKs remain; a deferred lineage constraint requires the actual parent attempt/checkpoint and same or ancestor Task, without weakening immutable triggers.

Revision 0010 preserves insertion order for control/input dispositions, including equal timestamps. Stage4 independent TaskDerivation has a NULL task parent in the source service, so its lineage is validated against the immutable derivation record, source checkpoint/attempt and common owner. Parent-bound imported derivations remain valid; independent forged references fail closed. The attempt lineage constraint is deferred only while the same transaction constructs the derivation closure; immutable triggers remain enabled.

Revision 0011 retains the actual candidate boundary checkpoint independently of the earlier inner provisional artifact checkpoint. Candidate-to-artifact FK remains pinned to the same workspace/Task/Goal/Attempt; both immutable parent checkpoints retain their own existing root FKs.
