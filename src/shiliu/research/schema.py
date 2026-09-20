from __future__ import annotations

import sqlite3


RESEARCH_STATE_SCHEMA_VERSION = "v5-a-stage1-state-v1"
INNER_RESEARCH_STATE_SCHEMA_VERSION = "v5-a-stage2-inner-state-v1"
INNER_ACTION_SCHEMA_VERSION = "v5-a-stage2-action-v1"
EVIDENCE_USE_SCHEMA_VERSION = "v5-a-stage2-evidence-use-v1"
EVIDENCE_VALIDATION_POLICY_VERSION = "v5-a-stage2-currentness-v1"
PROVISIONAL_ARTIFACT_SCHEMA_VERSION = "v5-a-stage2-provisional-artifact-v1"
CONSTRAINT_SPEC_SCHEMA_VERSION = "v5-a-stage3-constraint-spec-v1"
OUTER_AUDIT_SCHEMA_VERSION = "v5-a-stage3-outer-audit-v1"
OUTER_STATE_SCHEMA_VERSION = "v5-a-stage3-outer-state-v1"
COMPACT_IMPROVEMENT_SCHEMA_VERSION = "v5-a-stage3-improvement-v1"
CONTINUATION_SEED_SCHEMA_VERSION = "v5-a-stage3-continuation-seed-v1"
CONTROL_SCHEMA_VERSION = "v5-a-stage4-control-v1"
INPUT_SCHEMA_VERSION = "v5-a-stage4-input-v1"
DERIVATION_SCHEMA_VERSION = "v5-a-stage4-derivation-v1"
KNOWLEDGE_WORKSPACE_SCHEMA_VERSION = "v5-b-stage2-knowledge-workspace-v1"
KNOWLEDGE_DRAFT_SCHEMA_VERSION = "v5.6-knowledge-draft-v1"


def prepare_knowledge_draft_schema_v17(connection: sqlite3.Connection) -> None:
    """Add the isolated, non-authoritative Draft revision aggregate."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_draft_revisions (
            draft_revision_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            draft_schema_version TEXT NOT NULL
                CHECK(draft_schema_version='v5.6-knowledge-draft-v1'),
            version INTEGER NOT NULL CHECK(version >= 1),
            parent_revision_id TEXT REFERENCES knowledge_draft_revisions(draft_revision_id)
                ON DELETE RESTRICT,
            owner_scope TEXT NOT NULL CHECK(owner_scope='local_user_workspace'),
            origin_kind TEXT NOT NULL CHECK(origin_kind IN ('fast','deep','research')),
            ask_run_id TEXT REFERENCES ask_runs(run_id) ON DELETE RESTRICT,
            research_task_id TEXT REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            source_answer_snapshot_json TEXT NOT NULL,
            source_answer_hash TEXT NOT NULL,
            evidence_refs_json TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            revalidation_state TEXT NOT NULL CHECK(revalidation_state IN
                ('not_checked','current','needs_revalidation','blocked')),
            status TEXT NOT NULL CHECK(status IN
                ('saved','materializing','promotion_ready','needs_revalidation',
                 'confirmed','failed','cancelled')),
            dedupe_identity TEXT NOT NULL,
            materialization_task_id TEXT REFERENCES research_tasks(task_id)
                ON DELETE RESTRICT,
            candidate_ids_json TEXT NOT NULL DEFAULT '[]',
            promotion_output_json TEXT NOT NULL DEFAULT '{}',
            event_kind TEXT NOT NULL CHECK(event_kind IN
                ('saved','materialization_started','materialization_ready',
                 'materialization_failed','revalidation_blocked',
                 'promotion_confirmed','operation_failed',
                 'cancelled')),
            command_id TEXT NOT NULL,
            command_payload_hash TEXT NOT NULL,
            reason_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(draft_id, version),
            UNIQUE(draft_id, command_id),
            CHECK((origin_kind IN ('fast','deep') AND ask_run_id IS NOT NULL
                   AND research_task_id IS NULL)
               OR (origin_kind='research' AND ask_run_id IS NULL
                   AND research_task_id IS NOT NULL)),
            CHECK((version=1 AND parent_revision_id IS NULL)
               OR (version>1 AND parent_revision_id IS NOT NULL)),
            CHECK(version > 1 OR status <> 'confirmed')
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_draft_initial_dedupe
            ON knowledge_draft_revisions(owner_scope, dedupe_identity)
            WHERE version=1;
        CREATE INDEX IF NOT EXISTS idx_knowledge_draft_latest
            ON knowledge_draft_revisions(owner_scope, draft_id, version DESC);

        CREATE TRIGGER IF NOT EXISTS trg_knowledge_draft_revisions_no_update
        BEFORE UPDATE ON knowledge_draft_revisions
        BEGIN SELECT RAISE(ABORT, 'knowledge draft revisions are immutable'); END;

        CREATE TRIGGER IF NOT EXISTS trg_knowledge_draft_revisions_no_delete
        BEFORE DELETE ON knowledge_draft_revisions
        BEGIN SELECT RAISE(ABORT, 'knowledge draft revisions are immutable'); END;
        """
    )
KNOWLEDGE_VALIDATION_POLICY_VERSION = "v5-b-stage1-current-evidence-v1"
KNOWLEDGE_ARTIFACT_POLICY_VERSION = "v5-b-stage1-artifact-build-v1"
TOPIC_PAGE_POLICY_VERSION = "v5-b-stage1-topic-page-build-v1"
KNOWLEDGE_REVALIDATION_POLICY_VERSION = "v5-b-stage2-revalidation-v1"
KNOWLEDGE_UPDATE_POLICY_VERSION = "v5-b-stage2-update-v1"
KNOWLEDGE_EXPORT_POLICY_VERSION = "v5-b-stage2-export-v1"
ARTIFACT_ROUTE_POLICY_VERSION = "v5-b-stage3-artifact-route-v1"
PERSONAL_WORKSPACE_POLICY_VERSION = "v5-b-stage4-personal-workspace-v1"


def prepare_research_schema_v14(connection: sqlite3.Connection) -> None:
    """Add the single append-only Stage 4 WorkspaceRecord aggregate."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_workspace_records (
            record_revision_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            parent_revision_id TEXT REFERENCES research_workspace_records(record_revision_id) ON DELETE RESTRICT,
            command_task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            record_kind TEXT NOT NULL CHECK(record_kind IN (
                'explicit_memory', 'inferred_candidate', 'focus_state',
                'progress_observation', 'corpus_observation', 'system_experience'
            )),
            authority_class TEXT NOT NULL CHECK(authority_class IN (
                'user_authored', 'user_confirmed', 'behavioral_candidate',
                'evidence_backed_observation', 'corpus_soft_prior',
                'experience_candidate'
            )),
            status TEXT NOT NULL CHECK(status IN (
                'current', 'candidate', 'confirmed', 'rejected', 'expired',
                'tombstoned', 'superseded', 'invalidated', 'observed',
                'diagnosed', 'candidate_source'
            )),
            semantic_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            source_boundary_hash TEXT NOT NULL,
            confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            expires_at TEXT,
            decision_action TEXT NOT NULL,
            reason TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            command_id TEXT NOT NULL,
            command_payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(record_id, version),
            UNIQUE(command_task_id, command_id)
        );

        CREATE INDEX IF NOT EXISTS idx_research_workspace_records_projection
        ON research_workspace_records(record_kind, semantic_key, record_id, version);

        CREATE TRIGGER IF NOT EXISTS trg_research_workspace_records_immutable_update
        BEFORE UPDATE ON research_workspace_records BEGIN
            SELECT RAISE(ABORT, 'WorkspaceRecord revisions are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_research_workspace_records_immutable_delete
        BEFORE DELETE ON research_workspace_records BEGIN
            SELECT RAISE(ABORT, 'WorkspaceRecord revisions are immutable');
        END;
        """
    )


def prepare_research_schema_v13(connection: sqlite3.Connection) -> None:
    """Add the lean append-only Stage 3 ArtifactRoute aggregate."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_artifact_routes (
            record_id TEXT PRIMARY KEY,
            route_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            parent_record_id TEXT REFERENCES research_artifact_routes(record_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            record_kind TEXT NOT NULL CHECK(record_kind IN ('assessment', 'proceed', 'outcome')),
            command_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            query_json TEXT NOT NULL,
            retrieval_json TEXT NOT NULL,
            gates_json TEXT NOT NULL,
            recommended_route TEXT NOT NULL CHECK(recommended_route IN ('direct_reuse', 'incremental_refresh', 'research_seed')),
            final_route TEXT CHECK(final_route IS NULL OR final_route IN ('direct_reuse', 'incremental_refresh', 'research_seed')),
            expected_authority_hash TEXT NOT NULL,
            continuation_task_id TEXT REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            outcome_artifact_revision_id TEXT REFERENCES research_knowledge_artifact_revisions(artifact_revision_id) ON DELETE RESTRICT,
            contribution_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('assessed', 'running', 'completed', 'needs_user', 'superseded')),
            created_at TEXT NOT NULL,
            UNIQUE(route_id, version),
            UNIQUE(task_id, command_id)
        );

        CREATE INDEX IF NOT EXISTS idx_research_artifact_routes_task
        ON research_artifact_routes(task_id, created_at, route_id, version);

        CREATE TRIGGER IF NOT EXISTS trg_research_artifact_routes_immutable_update
        BEFORE UPDATE ON research_artifact_routes BEGIN
            SELECT RAISE(ABORT, 'ArtifactRoute records are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_research_artifact_routes_immutable_delete
        BEFORE DELETE ON research_artifact_routes BEGIN
            SELECT RAISE(ABORT, 'ArtifactRoute records are immutable');
        END;
        """
    )


def prepare_research_schema_v12(connection: sqlite3.Connection) -> None:
    """Expand the Stage 1 Topic Page tables without rewriting revision bodies."""
    row = connection.execute(
        "SELECT sql FROM sqlite_schema "
        "WHERE type='table' AND name='research_topic_page_revisions'"
    ).fetchone()
    if row is None or "CHECK(version = 1)" not in str(row[0]):
        return
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA legacy_alter_table = ON")
    try:
        connection.executescript(
            """
            CREATE TABLE research_topic_pages_v12 (
                page_id TEXT PRIMARY KEY,
                workspace_schema_version TEXT NOT NULL,
                task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
                slug TEXT NOT NULL UNIQUE,
                current_version INTEGER NOT NULL CHECK(current_version >= 1),
                published_version INTEGER CHECK(
                    published_version IS NULL OR
                    (published_version >= 1 AND published_version <= current_version)
                ),
                review_status TEXT NOT NULL CHECK(review_status IN ('draft', 'published', 'returned')),
                state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO research_topic_pages_v12(
                page_id, workspace_schema_version, task_id, slug,
                current_version, published_version, review_status,
                state_version, created_at, updated_at
            )
            SELECT page_id, workspace_schema_version, task_id, slug,
                   current_version,
                   CASE WHEN review_status='published' THEN current_version ELSE NULL END,
                   review_status, state_version, created_at, updated_at
            FROM research_topic_pages;

            CREATE TABLE research_topic_page_revisions_v12 (
                page_revision_id TEXT PRIMARY KEY,
                page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id) ON DELETE RESTRICT,
                task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
                version INTEGER NOT NULL CHECK(version >= 1),
                parent_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
                supersedes_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
                revert_of_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
                revision_kind TEXT NOT NULL CHECK(revision_kind IN ('initial', 'refresh', 'edit', 'revert')),
                artifact_revision_id TEXT NOT NULL REFERENCES research_knowledge_artifact_revisions(artifact_revision_id) ON DELETE RESTRICT,
                title TEXT NOT NULL CHECK(length(trim(title)) > 0),
                body_json TEXT NOT NULL,
                build_policy_version TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(page_id, version),
                UNIQUE(task_id, input_hash)
            );
            INSERT INTO research_topic_page_revisions_v12(
                page_revision_id, page_id, task_id, version,
                parent_revision_id, supersedes_revision_id,
                revert_of_revision_id, revision_kind,
                artifact_revision_id, title, body_json, build_policy_version,
                input_hash, content_hash, created_at
            )
            SELECT page_revision_id, page_id, task_id, version,
                   parent_revision_id, supersedes_revision_id,
                   NULL, 'initial', artifact_revision_id, title, body_json,
                   build_policy_version, input_hash, content_hash, created_at
            FROM research_topic_page_revisions;

            CREATE TABLE research_topic_page_review_decisions_v12 (
                decision_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
                page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id) ON DELETE RESTRICT,
                page_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
                decision_kind TEXT NOT NULL CHECK(decision_kind IN ('publish', 'return')),
                reason TEXT NOT NULL,
                expected_version INTEGER NOT NULL CHECK(expected_version >= 1),
                command_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(task_id, command_id)
            );
            INSERT INTO research_topic_page_review_decisions_v12
            SELECT * FROM research_topic_page_review_decisions;

            DROP TABLE research_topic_page_review_decisions;
            DROP TABLE research_topic_page_revisions;
            DROP TABLE research_topic_pages;
            ALTER TABLE research_topic_pages_v12 RENAME TO research_topic_pages;
            ALTER TABLE research_topic_page_revisions_v12 RENAME TO research_topic_page_revisions;
            ALTER TABLE research_topic_page_review_decisions_v12 RENAME TO research_topic_page_review_decisions;
            """
        )
        connection.commit()
    finally:
        connection.execute("PRAGMA legacy_alter_table = OFF")
        connection.execute("PRAGMA foreign_keys = ON")


def prepare_research_schema_v10(connection: sqlite3.Connection) -> None:
    """Add the Stage 4 control fence without rewriting existing aggregates."""
    task = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='research_tasks'"
    ).fetchone()
    if task is None:
        return
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(research_tasks)")
    }
    if "control_generation" not in columns:
        connection.execute(
            "ALTER TABLE research_tasks ADD COLUMN control_generation "
            "INTEGER NOT NULL DEFAULT 0 CHECK(control_generation >= 0)"
        )


def prepare_research_schema_v9(connection: sqlite3.Connection) -> None:
    """Expand the Stage 1 Result enum without rewriting any persisted Result."""
    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type='table' AND name='research_results'"
    ).fetchone()
    if row is None or "targeted_continuation" in str(row[0]):
        return
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            CREATE TABLE research_results_v9 (
                result_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
                goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
                attempt_id TEXT REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
                checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
                answer_status TEXT NOT NULL CHECK (
                    answer_status IN (
                        'valid_success', 'valid_partial',
                        'valid_insufficient', 'not_produced'
                    )
                ),
                termination_reason TEXT NOT NULL CHECK (
                    termination_reason IN (
                        'answer_ready', 'budget_exhausted', 'no_new_evidence',
                        'repeated_action', 'evidence_unavailable',
                        'needs_user_input', 'cancelled', 'goal_revised',
                        'external_side_effect_unknown', 'provider_error',
                        'implementation_error', 'targeted_continuation',
                        'constraint_unsatisfied'
                    )
                ),
                failure_class TEXT NOT NULL CHECK (
                    failure_class IN (
                        'none', 'implementation_failure', 'provider_failure',
                        'product_quality_failure', 'infrastructure_invalid_run',
                        'evaluation_invalid_run'
                    )
                ),
                reason_detail TEXT NOT NULL,
                is_task_terminal INTEGER NOT NULL CHECK (is_task_terminal IN (0, 1)),
                owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
                created_at TEXT NOT NULL
            );
            INSERT INTO research_results_v9
            SELECT * FROM research_results;
            DROP TABLE research_results;
            ALTER TABLE research_results_v9 RENAME TO research_results;
            """
        )
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def initialize_research_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_tasks (
            task_id TEXT PRIMARY KEY,
            parent_task_id TEXT REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (
                status IN ('ready', 'running', 'blocked', 'waiting_user', 'terminal')
            ),
            active_goal_id TEXT REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            state_version INTEGER NOT NULL DEFAULT 0 CHECK (state_version >= 0),
            owner_id TEXT,
            owner_epoch INTEGER NOT NULL DEFAULT 0 CHECK (owner_epoch >= 0),
            control_generation INTEGER NOT NULL DEFAULT 0 CHECK (control_generation >= 0),
            lease_until TEXT,
            terminal_result_id TEXT REFERENCES research_results(result_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                (status = 'terminal' AND terminal_result_id IS NOT NULL)
                OR (status != 'terminal' AND terminal_result_id IS NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS research_goals (
            goal_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            parent_goal_id TEXT REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            objective TEXT NOT NULL CHECK (length(trim(objective)) > 0),
            success_constraints_json TEXT NOT NULL,
            evidence_policy_json TEXT NOT NULL,
            created_by_event_id TEXT REFERENCES research_events(event_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, revision)
        );

        CREATE TABLE IF NOT EXISTS research_attempts (
            attempt_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
            cause TEXT NOT NULL CHECK (
                cause IN ('initial', 'resume', 'retry', 'goal_revision', 'branch', 'replay')
            ),
            parent_attempt_id TEXT REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            source_checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (
                status IN ('pending', 'running', 'blocked', 'waiting_user', 'terminal')
            ),
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            result_id TEXT REFERENCES research_results(result_id) ON DELETE RESTRICT,
            started_at TEXT,
            ended_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, ordinal)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_research_attempts_one_active
        ON research_attempts(task_id)
        WHERE status != 'terminal';

        CREATE TABLE IF NOT EXISTS research_checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            parent_checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence >= 1),
            state_schema_version TEXT NOT NULL,
            state_hash TEXT NOT NULL,
            state_payload_json TEXT NOT NULL,
            is_complete INTEGER NOT NULL CHECK (is_complete IN (0, 1)),
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL,
            UNIQUE(attempt_id, sequence)
        );

        CREATE TABLE IF NOT EXISTS research_events (
            event_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence >= 1),
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            command_id TEXT,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 0),
            created_at TEXT NOT NULL,
            UNIQUE(task_id, sequence)
        );

        CREATE TABLE IF NOT EXISTS research_traces (
            trace_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            trace_schema_version TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            termination_reason TEXT,
            retention_class TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_results (
            result_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            answer_status TEXT NOT NULL CHECK (
                answer_status IN (
                    'valid_success', 'valid_partial', 'valid_insufficient', 'not_produced'
                )
            ),
            termination_reason TEXT NOT NULL CHECK (
                termination_reason IN (
                    'answer_ready', 'budget_exhausted', 'no_new_evidence',
                    'repeated_action', 'evidence_unavailable', 'needs_user_input',
                    'cancelled', 'goal_revised', 'external_side_effect_unknown',
                    'provider_error', 'implementation_error',
                    'targeted_continuation', 'constraint_unsatisfied'
                )
            ),
            failure_class TEXT NOT NULL CHECK (
                failure_class IN (
                    'none', 'implementation_failure', 'provider_failure',
                    'product_quality_failure', 'infrastructure_invalid_run',
                    'evaluation_invalid_run'
                )
            ),
            reason_detail TEXT NOT NULL,
            is_task_terminal INTEGER NOT NULL CHECK (is_task_terminal IN (0, 1)),
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_command_receipts (
            receipt_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            command_type TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('accepted', 'committed', 'rejected')),
            outcome_reference TEXT,
            response_json TEXT,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 0),
            created_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_side_effects (
            side_effect_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            effect_kind TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            request_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('reserved', 'in_flight', 'succeeded', 'failed', 'unknown')
            ),
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            provider_operation_id TEXT,
            receipt_hash TEXT,
            result_reference TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(task_id, effect_kind, idempotency_key)
        );

        CREATE TABLE IF NOT EXISTS research_inner_actions (
            action_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            originating_checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            action_kind TEXT NOT NULL CHECK (
                action_kind IN (
                    'plan', 'navigation', 'transcript_search',
                    'transcript_window', 'provisional_synthesis'
                )
            ),
            action_schema_version TEXT NOT NULL,
            action_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            request_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN (
                    'planned', 'reserved', 'running', 'succeeded',
                    'failed', 'unknown', 'rejected'
                )
            ),
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            retrieval_execution_id TEXT,
            retrieval_trace_id TEXT,
            side_effect_id TEXT REFERENCES research_side_effects(side_effect_id) ON DELETE RESTRICT,
            observation_json TEXT NOT NULL,
            error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(attempt_id, action_key)
        );

        CREATE TABLE IF NOT EXISTS research_evidence_identities (
            evidence_id TEXT PRIMARY KEY,
            citation_identity_version TEXT NOT NULL,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE RESTRICT,
            source_artifact_id TEXT NOT NULL,
            source_version TEXT NOT NULL,
            timeline_run_id TEXT NOT NULL,
            segment_ids_json TEXT NOT NULL,
            segment_ordinals_json TEXT NOT NULL,
            start_time REAL NOT NULL CHECK (start_time >= 0),
            end_time REAL NOT NULL CHECK (end_time >= start_time),
            quote_hash TEXT NOT NULL,
            quote_preview TEXT NOT NULL,
            identity_payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_evidence_uses (
            evidence_use_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL REFERENCES research_evidence_identities(evidence_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            first_action_id TEXT NOT NULL REFERENCES research_inner_actions(action_id) ON DELETE RESTRICT,
            originating_checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            use_purpose TEXT NOT NULL,
            use_schema_version TEXT NOT NULL,
            use_payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, attempt_id, evidence_id)
        );

        CREATE TABLE IF NOT EXISTS research_evidence_provenance (
            provenance_id TEXT PRIMARY KEY,
            evidence_use_id TEXT NOT NULL REFERENCES research_evidence_uses(evidence_use_id) ON DELETE RESTRICT,
            action_id TEXT NOT NULL REFERENCES research_inner_actions(action_id) ON DELETE RESTRICT,
            execution_id TEXT,
            search_trace_id TEXT,
            query_fingerprint TEXT NOT NULL,
            rank INTEGER,
            retrieval_method TEXT NOT NULL,
            index_identity_json TEXT NOT NULL,
            parent_chunk_ids_json TEXT NOT NULL,
            source_version_authority TEXT NOT NULL,
            mapping_policy_versions_json TEXT NOT NULL,
            provenance_hash TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            UNIQUE(evidence_use_id, provenance_hash)
        );

        CREATE TABLE IF NOT EXISTS research_evidence_validations (
            observation_id TEXT PRIMARY KEY,
            evidence_use_id TEXT NOT NULL REFERENCES research_evidence_uses(evidence_use_id) ON DELETE RESTRICT,
            evidence_id TEXT NOT NULL REFERENCES research_evidence_identities(evidence_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            validation_policy_version TEXT NOT NULL,
            authority_mode TEXT NOT NULL,
            expected_source_version TEXT NOT NULL,
            observed_source_version TEXT,
            outcome TEXT NOT NULL CHECK (
                outcome IN ('current', 'stale', 'missing', 'invalid', 'error')
            ),
            reason_code TEXT NOT NULL,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            observed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_provisional_artifacts (
            artifact_id TEXT PRIMARY KEY,
            artifact_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            checkpoint_id TEXT NOT NULL REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            objective TEXT NOT NULL,
            answer_status TEXT NOT NULL CHECK (
                answer_status IN ('valid_success', 'valid_partial', 'valid_insufficient')
            ),
            answer_blocks_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            evidence_set_fingerprint TEXT NOT NULL,
            evidence_use_ids_json TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            validation_observation_ids_json TEXT NOT NULL,
            generation_policy_version TEXT NOT NULL,
            validator_policy_version TEXT NOT NULL,
            provider_side_effect_id TEXT REFERENCES research_side_effects(side_effect_id) ON DELETE RESTRICT,
            artifact_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_constraint_specs (
            constraint_id TEXT PRIMARY KEY,
            constraint_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            goal_revision INTEGER NOT NULL CHECK (goal_revision >= 1),
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            constraint_scope TEXT NOT NULL CHECK (
                constraint_scope IN ('objective', 'success_constraint')
            ),
            original_text TEXT NOT NULL CHECK (length(trim(original_text)) > 0),
            normalized_text TEXT NOT NULL CHECK (length(trim(normalized_text)) > 0),
            constraint_kind TEXT NOT NULL,
            is_required INTEGER NOT NULL CHECK (is_required IN (0, 1)),
            evaluator_policy_json TEXT NOT NULL,
            evaluator_policy_version TEXT NOT NULL,
            canonical_payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(goal_id, ordinal)
        );

        CREATE TABLE IF NOT EXISTS research_audit_candidates (
            candidate_id TEXT PRIMARY KEY,
            candidate_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            producer_kind TEXT NOT NULL CHECK (
                producer_kind IN ('deterministic', 'provider')
            ),
            proposal_json TEXT NOT NULL,
            proposal_hash TEXT NOT NULL,
            provider_side_effect_id TEXT REFERENCES research_side_effects(side_effect_id) ON DELETE RESTRICT,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_outer_audits (
            audit_id TEXT PRIMARY KEY,
            audit_schema_version TEXT NOT NULL,
            audit_policy_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            source_checkpoint_id TEXT NOT NULL REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            constraint_snapshot_hash TEXT NOT NULL,
            observation_ids_json TEXT NOT NULL,
            validation_observation_ids_json TEXT NOT NULL,
            artifact_fingerprint TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            progress_fingerprint TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (
                outcome IN (
                    'accept', 'targeted_continue', 'stop_partial',
                    'stop_insufficient', 'blocked', 'failed'
                )
            ),
            blocker TEXT,
            reason_codes_json TEXT NOT NULL,
            budget_before_json TEXT NOT NULL,
            budget_after_json TEXT NOT NULL,
            candidate_id TEXT REFERENCES research_audit_candidates(candidate_id) ON DELETE RESTRICT,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_constraint_audit_observations (
            audit_observation_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES research_outer_audits(audit_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            constraint_id TEXT NOT NULL REFERENCES research_constraint_specs(constraint_id) ON DELETE RESTRICT,
            evaluator_policy_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('satisfied', 'unsatisfied', 'unknown', 'invalid')
            ),
            recoverability TEXT NOT NULL CHECK (
                recoverability IN (
                    'recoverable', 'irrecoverable', 'needs_user', 'not_applicable'
                )
            ),
            evidence_use_ids_json TEXT NOT NULL,
            validation_observation_ids_json TEXT NOT NULL,
            reason_codes_json TEXT NOT NULL,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            observed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_compact_improvement_states (
            improvement_state_id TEXT PRIMARY KEY,
            improvement_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            audit_id TEXT NOT NULL REFERENCES research_outer_audits(audit_id) ON DELETE RESTRICT,
            source_checkpoint_id TEXT NOT NULL REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            state_payload_json TEXT NOT NULL,
            state_hash TEXT NOT NULL,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_continuation_decisions (
            continuation_decision_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            parent_attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            child_attempt_id TEXT REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            audit_id TEXT NOT NULL REFERENCES research_outer_audits(audit_id) ON DELETE RESTRICT,
            improvement_state_id TEXT NOT NULL REFERENCES research_compact_improvement_states(improvement_state_id) ON DELETE RESTRICT,
            decision TEXT NOT NULL CHECK (
                decision IN (
                    'accept', 'targeted_continue', 'stop_partial',
                    'stop_insufficient', 'blocked'
                )
            ),
            targeted_objective TEXT,
            target_fingerprint TEXT,
            reason_codes_json TEXT NOT NULL,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL,
            CHECK (
                (decision = 'targeted_continue' AND child_attempt_id IS NOT NULL
                    AND targeted_objective IS NOT NULL AND target_fingerprint IS NOT NULL)
                OR
                (decision != 'targeted_continue' AND child_attempt_id IS NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS research_continuation_seeds (
            seed_id TEXT PRIMARY KEY,
            seed_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            parent_attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            child_attempt_id TEXT NOT NULL UNIQUE REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            continuation_decision_id TEXT NOT NULL UNIQUE REFERENCES research_continuation_decisions(continuation_decision_id) ON DELETE RESTRICT,
            audit_id TEXT NOT NULL REFERENCES research_outer_audits(audit_id) ON DELETE RESTRICT,
            source_checkpoint_id TEXT NOT NULL REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            source_artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            targeted_objective TEXT NOT NULL CHECK (length(trim(targeted_objective)) > 0),
            target_fingerprint TEXT NOT NULL,
            carry_evidence_ids_json TEXT NOT NULL,
            seed_payload_hash TEXT NOT NULL,
            owner_epoch INTEGER NOT NULL CHECK (owner_epoch >= 1),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_outer_result_links (
            result_id TEXT PRIMARY KEY REFERENCES research_results(result_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            audit_id TEXT NOT NULL REFERENCES research_outer_audits(audit_id) ON DELETE RESTRICT,
            artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            constraint_fingerprint TEXT NOT NULL,
            validation_observation_ids_json TEXT NOT NULL,
            generation_policy_version TEXT NOT NULL,
            audit_policy_version TEXT NOT NULL,
            evaluator_policy_versions_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_control_requests (
            control_request_id TEXT PRIMARY KEY,
            control_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            attempt_id TEXT REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            request_kind TEXT NOT NULL CHECK (
                request_kind IN ('interrupt', 'resume', 'cancel')
            ),
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            audit_actor_metadata_json TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            expected_state_version INTEGER NOT NULL CHECK(expected_state_version >= 0),
            expected_checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            expected_control_generation INTEGER NOT NULL CHECK(expected_control_generation >= 0),
            admitted_control_generation INTEGER NOT NULL CHECK(admitted_control_generation >= 1),
            admitted_owner_epoch INTEGER NOT NULL CHECK(admitted_owner_epoch >= 1),
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_control_dispositions (
            disposition_id TEXT PRIMARY KEY,
            control_request_id TEXT NOT NULL REFERENCES research_control_requests(control_request_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (
                status IN ('accepted', 'applied', 'rejected', 'superseded')
            ),
            observed_control_generation INTEGER NOT NULL CHECK(observed_control_generation >= 1),
            owner_epoch INTEGER NOT NULL CHECK(owner_epoch >= 1),
            reason TEXT NOT NULL,
            resulting_references_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_input_requests (
            input_request_id TEXT PRIMARY KEY,
            input_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            source_checkpoint_id TEXT NOT NULL REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            request_kind TEXT NOT NULL CHECK (
                request_kind IN ('clarification', 'constraint_choice')
            ),
            prompt TEXT NOT NULL CHECK(length(prompt) BETWEEN 1 AND 2000),
            choices_json TEXT NOT NULL,
            response_schema_json TEXT NOT NULL,
            constraint_id TEXT REFERENCES research_constraint_specs(constraint_id) ON DELETE RESTRICT,
            payload_hash TEXT NOT NULL,
            owner_epoch INTEGER NOT NULL CHECK(owner_epoch >= 1),
            expires_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_input_dispositions (
            disposition_id TEXT PRIMARY KEY,
            input_request_id TEXT NOT NULL REFERENCES research_input_requests(input_request_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (
                status IN ('open', 'resolved', 'cancelled', 'superseded')
            ),
            control_generation INTEGER NOT NULL CHECK(control_generation >= 0),
            reason TEXT NOT NULL,
            resulting_reference TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_human_decisions (
            decision_id TEXT PRIMARY KEY,
            input_request_id TEXT NOT NULL UNIQUE REFERENCES research_input_requests(input_request_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            decision_kind TEXT NOT NULL CHECK (
                decision_kind IN ('clarify_goal', 'select_constraint_option')
            ),
            response_hash TEXT NOT NULL,
            response_json TEXT NOT NULL,
            applied_action TEXT NOT NULL,
            result_references_json TEXT NOT NULL,
            control_generation INTEGER NOT NULL CHECK(control_generation >= 1),
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_human_constraint_observations (
            observation_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            constraint_id TEXT NOT NULL REFERENCES research_constraint_specs(constraint_id) ON DELETE RESTRICT,
            decision_id TEXT NOT NULL UNIQUE REFERENCES research_human_decisions(decision_id) ON DELETE RESTRICT,
            selected_option TEXT NOT NULL,
            evaluator_policy_version TEXT NOT NULL,
            control_generation INTEGER NOT NULL CHECK(control_generation >= 1),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_side_effect_resolutions (
            resolution_id TEXT PRIMARY KEY,
            side_effect_id TEXT NOT NULL UNIQUE REFERENCES research_side_effects(side_effect_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            resolution TEXT NOT NULL CHECK (
                resolution IN ('confirmed_succeeded', 'confirmed_failed')
            ),
            reason TEXT NOT NULL,
            receipt_hash TEXT,
            result_reference TEXT,
            control_generation INTEGER NOT NULL CHECK(control_generation >= 1),
            owner_epoch INTEGER NOT NULL CHECK(owner_epoch >= 1),
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id),
            CHECK (
                resolution != 'confirmed_succeeded'
                OR (receipt_hash IS NOT NULL AND result_reference IS NOT NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS research_task_derivations (
            derivation_id TEXT PRIMARY KEY,
            derivation_schema_version TEXT NOT NULL,
            source_task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            source_goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            source_attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            source_checkpoint_id TEXT NOT NULL REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            child_task_id TEXT NOT NULL UNIQUE REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            child_goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            child_attempt_id TEXT NOT NULL UNIQUE REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            command_id TEXT NOT NULL,
            derivation_kind TEXT NOT NULL CHECK(derivation_kind IN ('branch', 'replay')),
            source_state_hash TEXT NOT NULL,
            source_manifest_json TEXT NOT NULL,
            goal_delta_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(source_task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_candidates (
            candidate_id TEXT PRIMARY KEY,
            workspace_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            goal_id TEXT NOT NULL REFERENCES research_goals(goal_id) ON DELETE RESTRICT,
            attempt_id TEXT NOT NULL REFERENCES research_attempts(attempt_id) ON DELETE RESTRICT,
            checkpoint_id TEXT REFERENCES research_checkpoints(checkpoint_id) ON DELETE RESTRICT,
            result_id TEXT REFERENCES research_results(result_id) ON DELETE RESTRICT,
            provisional_artifact_id TEXT NOT NULL REFERENCES research_provisional_artifacts(artifact_id) ON DELETE RESTRICT,
            source_event_id TEXT NOT NULL REFERENCES research_events(event_id) ON DELETE RESTRICT,
            source_delta_snapshot_id TEXT NOT NULL,
            candidate_kind TEXT NOT NULL CHECK(candidate_kind='KnowledgeDelta'),
            source_boundary_hash TEXT NOT NULL,
            source_delta_hash TEXT NOT NULL,
            source_item_hash TEXT NOT NULL,
            source_item_index INTEGER NOT NULL CHECK(source_item_index >= 0),
            parent_candidate_id TEXT REFERENCES research_knowledge_candidates(candidate_id) ON DELETE RESTRICT,
            claim_text TEXT NOT NULL CHECK(length(trim(claim_text)) > 0),
            citation_ids_json TEXT NOT NULL,
            evidence_use_ids_json TEXT NOT NULL,
            source_payload_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN (
                    'pending_review', 'needs_revalidation', 'accepted',
                    'rejected', 'superseded'
                )
            ),
            state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_event_id, source_item_hash)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_review_decisions (
            decision_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            candidate_id TEXT NOT NULL REFERENCES research_knowledge_candidates(candidate_id) ON DELETE RESTRICT,
            decision_kind TEXT NOT NULL CHECK(decision_kind IN ('accept', 'reject', 'edit')),
            reason TEXT NOT NULL,
            edited_candidate_id TEXT REFERENCES research_knowledge_candidates(candidate_id) ON DELETE RESTRICT,
            fact_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            expected_candidate_version INTEGER NOT NULL CHECK(expected_candidate_version >= 0),
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_grounded_facts (
            fact_id TEXT PRIMARY KEY,
            workspace_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            origin_candidate_id TEXT NOT NULL UNIQUE REFERENCES research_knowledge_candidates(candidate_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_fact_revisions (
            fact_revision_id TEXT PRIMARY KEY,
            fact_id TEXT NOT NULL REFERENCES research_grounded_facts(fact_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            parent_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            supersedes_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            origin_candidate_id TEXT NOT NULL REFERENCES research_knowledge_candidates(candidate_id) ON DELETE RESTRICT,
            claim_text TEXT NOT NULL CHECK(length(trim(claim_text)) > 0),
            temporal_scope_json TEXT NOT NULL,
            viewpoint_scope_json TEXT NOT NULL,
            verification_status TEXT NOT NULL CHECK(verification_status='accepted_current'),
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(fact_id, revision)
        );

        CREATE TABLE IF NOT EXISTS research_fact_evidence_links (
            link_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            evidence_id TEXT NOT NULL REFERENCES research_evidence_identities(evidence_id) ON DELETE RESTRICT,
            evidence_use_id TEXT NOT NULL REFERENCES research_evidence_uses(evidence_use_id) ON DELETE RESTRICT,
            validation_observation_id TEXT NOT NULL REFERENCES research_evidence_validations(observation_id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            created_at TEXT NOT NULL,
            UNIQUE(fact_revision_id, evidence_use_id)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_artifacts (
            artifact_id TEXT PRIMARY KEY,
            workspace_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_artifact_revisions (
            artifact_revision_id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL REFERENCES research_knowledge_artifacts(artifact_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            parent_revision_id TEXT REFERENCES research_knowledge_artifact_revisions(artifact_revision_id) ON DELETE RESTRICT,
            supersedes_revision_id TEXT REFERENCES research_knowledge_artifact_revisions(artifact_revision_id) ON DELETE RESTRICT,
            topic TEXT NOT NULL CHECK(length(trim(topic)) > 0),
            body_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            unresolved_json TEXT NOT NULL,
            build_policy_version TEXT NOT NULL,
            source_result_ids_json TEXT NOT NULL,
            source_boundary_hashes_json TEXT NOT NULL,
            corpus_snapshot_json TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(artifact_id, revision),
            UNIQUE(task_id, input_hash)
        );

        CREATE TABLE IF NOT EXISTS research_artifact_fact_links (
            link_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            artifact_revision_id TEXT NOT NULL REFERENCES research_knowledge_artifact_revisions(artifact_revision_id) ON DELETE RESTRICT,
            fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            created_at TEXT NOT NULL,
            UNIQUE(artifact_revision_id, fact_revision_id)
        );

        CREATE TABLE IF NOT EXISTS research_topic_pages (
            page_id TEXT PRIMARY KEY,
            workspace_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            slug TEXT NOT NULL UNIQUE,
            current_version INTEGER NOT NULL CHECK(current_version >= 1),
            published_version INTEGER CHECK(
                published_version IS NULL OR
                (published_version >= 1 AND published_version <= current_version)
            ),
            review_status TEXT NOT NULL CHECK(review_status IN ('draft', 'published', 'returned')),
            state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_topic_page_revisions (
            page_revision_id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            version INTEGER NOT NULL CHECK(version >= 1),
            parent_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            supersedes_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            revert_of_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            revision_kind TEXT NOT NULL CHECK(revision_kind IN ('initial', 'refresh', 'edit', 'revert')),
            artifact_revision_id TEXT NOT NULL REFERENCES research_knowledge_artifact_revisions(artifact_revision_id) ON DELETE RESTRICT,
            title TEXT NOT NULL CHECK(length(trim(title)) > 0),
            body_json TEXT NOT NULL,
            build_policy_version TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(page_id, version),
            UNIQUE(task_id, input_hash)
        );

        CREATE TABLE IF NOT EXISTS research_topic_page_fact_links (
            link_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            page_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            created_at TEXT NOT NULL,
            UNIQUE(page_revision_id, fact_revision_id)
        );

        CREATE TABLE IF NOT EXISTS research_topic_page_review_decisions (
            decision_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id) ON DELETE RESTRICT,
            page_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            decision_kind TEXT NOT NULL CHECK(decision_kind IN ('publish', 'return')),
            reason TEXT NOT NULL,
            expected_version INTEGER NOT NULL CHECK(expected_version >= 1),
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_build_runs (
            build_run_id TEXT PRIMARY KEY,
            workspace_schema_version TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            build_kind TEXT NOT NULL CHECK(build_kind IN ('artifact', 'topic_page')),
            command_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            input_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN ('queued', 'running', 'succeeded', 'failed')
            ),
            attempt_count INTEGER NOT NULL CHECK(attempt_count >= 1),
            output_reference TEXT,
            error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(task_id, build_kind, input_hash)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_fact_states (
            fact_id TEXT PRIMARY KEY REFERENCES research_grounded_facts(fact_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            current_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            lifecycle_status TEXT NOT NULL CHECK(lifecycle_status IN ('current', 'retired', 'superseded')),
            currentness_status TEXT NOT NULL CHECK(currentness_status IN ('current', 'stale', 'potential_conflict', 'conflicted')),
            superseded_by_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            latest_observation_set_id TEXT,
            state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_revalidation_observations (
            observation_id TEXT PRIMARY KEY,
            observation_set_id TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            evidence_id TEXT NOT NULL REFERENCES research_evidence_identities(evidence_id) ON DELETE RESTRICT,
            evidence_use_id TEXT NOT NULL REFERENCES research_evidence_uses(evidence_use_id) ON DELETE RESTRICT,
            validation_observation_id TEXT NOT NULL REFERENCES research_evidence_validations(observation_id) ON DELETE RESTRICT,
            trigger_kind TEXT NOT NULL CHECK(trigger_kind IN ('explicit', 'source_change', 'update_operation', 'recovery')),
            expected_source_version TEXT NOT NULL,
            observed_source_version TEXT,
            outcome TEXT NOT NULL CHECK(outcome IN ('current', 'stale', 'missing', 'invalid', 'error')),
            reason_code TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            UNIQUE(observation_set_id, evidence_use_id)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_update_candidates (
            update_candidate_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            fact_id TEXT NOT NULL REFERENCES research_grounded_facts(fact_id) ON DELETE RESTRICT,
            source_fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            related_fact_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            source_observation_set_id TEXT,
            candidate_kind TEXT NOT NULL CHECK(candidate_kind IN ('source_rebind', 'new_evidence', 'user_correction', 'potential_conflict', 'retire', 'supersede')),
            proposed_claim TEXT,
            temporal_scope_json TEXT NOT NULL,
            viewpoint_scope_json TEXT NOT NULL,
            evidence_use_ids_json TEXT NOT NULL,
            affected_artifact_ids_json TEXT NOT NULL,
            affected_page_ids_json TEXT NOT NULL,
            validator_status TEXT NOT NULL CHECK(validator_status IN ('eligible', 'needs_revalidation')),
            status TEXT NOT NULL CHECK(status IN ('pending_review', 'needs_revalidation', 'accepted', 'rejected', 'superseded')),
            parent_candidate_id TEXT REFERENCES research_knowledge_update_candidates(update_candidate_id) ON DELETE RESTRICT,
            state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_lifecycle_decisions (
            decision_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            fact_id TEXT NOT NULL REFERENCES research_grounded_facts(fact_id) ON DELETE RESTRICT,
            update_candidate_id TEXT NOT NULL REFERENCES research_knowledge_update_candidates(update_candidate_id) ON DELETE RESTRICT,
            decision_kind TEXT NOT NULL CHECK(decision_kind IN ('accept', 'reject', 'edit')),
            result_kind TEXT NOT NULL CHECK(result_kind IN ('correct', 'retire', 'supersede', 'confirm_conflict', 'reject', 'edit')),
            source_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            result_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            related_fact_revision_id TEXT REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            reason TEXT NOT NULL,
            expected_candidate_version INTEGER NOT NULL CHECK(expected_candidate_version >= 0),
            expected_fact_state_version INTEGER NOT NULL CHECK(expected_fact_state_version >= 0),
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_conflict_observations (
            conflict_observation_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            left_fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            right_fact_revision_id TEXT NOT NULL REFERENCES research_fact_revisions(fact_revision_id) ON DELETE RESTRICT,
            scope_overlap INTEGER NOT NULL CHECK(scope_overlap IN (0, 1)),
            resolution TEXT NOT NULL CHECK(resolution IN ('confirmed_conflict', 'different_scope', 'coexists')),
            update_candidate_id TEXT NOT NULL REFERENCES research_knowledge_update_candidates(update_candidate_id) ON DELETE RESTRICT,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_update_operations (
            operation_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            operation_kind TEXT NOT NULL CHECK(operation_kind IN ('refresh_knowledge', 'export_page')),
            target_reference TEXT NOT NULL,
            dedup_key TEXT NOT NULL,
            command_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            input_json TEXT NOT NULL,
            expected_heads_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'retry_wait', 'succeeded', 'needs_user', 'dead_letter', 'superseded', 'cancelled')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
            max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 10),
            error_class TEXT,
            error_code TEXT,
            error_detail TEXT,
            next_attempt_at TEXT,
            claimant_id TEXT,
            lease_until TEXT,
            claim_generation INTEGER NOT NULL DEFAULT 0 CHECK(claim_generation >= 0),
            output_reference TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT,
            UNIQUE(task_id, operation_kind, dedup_key)
        );

        CREATE TABLE IF NOT EXISTS research_topic_page_revision_decisions (
            decision_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id) ON DELETE RESTRICT,
            source_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            result_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            decision_kind TEXT NOT NULL CHECK(decision_kind IN ('edit', 'revert', 'refresh')),
            reason TEXT NOT NULL,
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id)
        );

        CREATE TABLE IF NOT EXISTS research_knowledge_exports (
            export_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            page_revision_id TEXT NOT NULL REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            export_format TEXT NOT NULL CHECK(export_format IN ('markdown', 'json')),
            content_hash TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            operation_id TEXT NOT NULL REFERENCES research_knowledge_update_operations(operation_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            UNIQUE(page_revision_id, export_format, content_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_research_tasks_parent
        ON research_tasks(parent_task_id);
        CREATE INDEX IF NOT EXISTS idx_research_tasks_status
        ON research_tasks(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_research_goals_task
        ON research_goals(task_id, revision);
        CREATE INDEX IF NOT EXISTS idx_research_attempts_task
        ON research_attempts(task_id, ordinal);
        CREATE INDEX IF NOT EXISTS idx_research_checkpoints_attempt
        ON research_checkpoints(attempt_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_research_events_task
        ON research_events(task_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_research_traces_task
        ON research_traces(task_id, started_at);
        CREATE INDEX IF NOT EXISTS idx_research_results_task
        ON research_results(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_side_effects_recovery
        ON research_side_effects(task_id, status, owner_epoch);
        CREATE INDEX IF NOT EXISTS idx_research_inner_actions_task
        ON research_inner_actions(task_id, attempt_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_evidence_uses_task
        ON research_evidence_uses(task_id, attempt_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_evidence_provenance_use
        ON research_evidence_provenance(evidence_use_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_research_evidence_validations_use
        ON research_evidence_validations(evidence_use_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_research_provisional_artifacts_task
        ON research_provisional_artifacts(task_id, attempt_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_constraint_specs_goal
        ON research_constraint_specs(task_id, goal_id, ordinal);
        CREATE INDEX IF NOT EXISTS idx_research_outer_audits_task
        ON research_outer_audits(task_id, goal_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_constraint_observations_audit
        ON research_constraint_audit_observations(audit_id, constraint_id);
        CREATE INDEX IF NOT EXISTS idx_research_continuation_decisions_task
        ON research_continuation_decisions(task_id, goal_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_control_requests_task
        ON research_control_requests(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_control_dispositions_request
        ON research_control_dispositions(control_request_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_input_requests_task
        ON research_input_requests(task_id, attempt_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_input_dispositions_request
        ON research_input_dispositions(input_request_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_derivations_source
        ON research_task_derivations(source_task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_knowledge_candidates_task
        ON research_knowledge_candidates(task_id, status, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_fact_revisions_task
        ON research_fact_revisions(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_artifact_revisions_task
        ON research_knowledge_artifact_revisions(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_topic_pages_task
        ON research_topic_pages(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_knowledge_build_runs_task
        ON research_knowledge_build_runs(task_id, build_kind, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_knowledge_observations_fact
        ON research_knowledge_revalidation_observations(fact_revision_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_research_knowledge_update_candidates_task
        ON research_knowledge_update_candidates(task_id, status, created_at);
        CREATE INDEX IF NOT EXISTS idx_research_knowledge_update_operations_recovery
        ON research_knowledge_update_operations(task_id, status, next_attempt_at, lease_until);

        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_identity_no_update
        BEFORE UPDATE ON research_evidence_identities
        BEGIN
            SELECT RAISE(ABORT, 'research evidence identity is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_identity_no_delete
        BEFORE DELETE ON research_evidence_identities
        BEGIN
            SELECT RAISE(ABORT, 'research evidence identity is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_use_no_update
        BEFORE UPDATE ON research_evidence_uses
        BEGIN
            SELECT RAISE(ABORT, 'research evidence use is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_use_no_delete
        BEFORE DELETE ON research_evidence_uses
        BEGIN
            SELECT RAISE(ABORT, 'research evidence use is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_provenance_no_update
        BEFORE UPDATE ON research_evidence_provenance
        BEGIN
            SELECT RAISE(ABORT, 'research evidence provenance is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_provenance_no_delete
        BEFORE DELETE ON research_evidence_provenance
        BEGIN
            SELECT RAISE(ABORT, 'research evidence provenance is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_validation_no_update
        BEFORE UPDATE ON research_evidence_validations
        BEGIN
            SELECT RAISE(ABORT, 'research evidence validation is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_evidence_validation_no_delete
        BEFORE DELETE ON research_evidence_validations
        BEGIN
            SELECT RAISE(ABORT, 'research evidence validation is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_provisional_artifact_no_update
        BEFORE UPDATE ON research_provisional_artifacts
        BEGIN
            SELECT RAISE(ABORT, 'research provisional artifact is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_provisional_artifact_no_delete
        BEFORE DELETE ON research_provisional_artifacts
        BEGIN
            SELECT RAISE(ABORT, 'research provisional artifact is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_constraint_spec_no_update
        BEFORE UPDATE ON research_constraint_specs BEGIN
            SELECT RAISE(ABORT, 'research constraint spec is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_constraint_spec_no_delete
        BEFORE DELETE ON research_constraint_specs BEGIN
            SELECT RAISE(ABORT, 'research constraint spec is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_outer_audit_no_update
        BEFORE UPDATE ON research_outer_audits BEGIN
            SELECT RAISE(ABORT, 'research outer audit is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_outer_audit_no_delete
        BEFORE DELETE ON research_outer_audits BEGIN
            SELECT RAISE(ABORT, 'research outer audit is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_constraint_observation_no_update
        BEFORE UPDATE ON research_constraint_audit_observations BEGIN
            SELECT RAISE(ABORT, 'research constraint observation is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_constraint_observation_no_delete
        BEFORE DELETE ON research_constraint_audit_observations BEGIN
            SELECT RAISE(ABORT, 'research constraint observation is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_improvement_state_no_update
        BEFORE UPDATE ON research_compact_improvement_states BEGIN
            SELECT RAISE(ABORT, 'research improvement state is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_improvement_state_no_delete
        BEFORE DELETE ON research_compact_improvement_states BEGIN
            SELECT RAISE(ABORT, 'research improvement state is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_continuation_seed_no_update
        BEFORE UPDATE ON research_continuation_seeds BEGIN
            SELECT RAISE(ABORT, 'research continuation seed is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_continuation_seed_no_delete
        BEFORE DELETE ON research_continuation_seeds BEGIN
            SELECT RAISE(ABORT, 'research continuation seed is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_control_request_no_update
        BEFORE UPDATE ON research_control_requests BEGIN
            SELECT RAISE(ABORT, 'research control request is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_control_request_no_delete
        BEFORE DELETE ON research_control_requests BEGIN
            SELECT RAISE(ABORT, 'research control request is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_control_disposition_no_update
        BEFORE UPDATE ON research_control_dispositions BEGIN
            SELECT RAISE(ABORT, 'research control disposition is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_control_disposition_no_delete
        BEFORE DELETE ON research_control_dispositions BEGIN
            SELECT RAISE(ABORT, 'research control disposition is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_input_request_no_update
        BEFORE UPDATE ON research_input_requests BEGIN
            SELECT RAISE(ABORT, 'research input request is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_input_request_no_delete
        BEFORE DELETE ON research_input_requests BEGIN
            SELECT RAISE(ABORT, 'research input request is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_input_disposition_no_update
        BEFORE UPDATE ON research_input_dispositions BEGIN
            SELECT RAISE(ABORT, 'research input disposition is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_input_disposition_no_delete
        BEFORE DELETE ON research_input_dispositions BEGIN
            SELECT RAISE(ABORT, 'research input disposition is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_human_decision_no_update
        BEFORE UPDATE ON research_human_decisions BEGIN
            SELECT RAISE(ABORT, 'research human decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_human_decision_no_delete
        BEFORE DELETE ON research_human_decisions BEGIN
            SELECT RAISE(ABORT, 'research human decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_human_constraint_observation_no_update
        BEFORE UPDATE ON research_human_constraint_observations BEGIN
            SELECT RAISE(ABORT, 'research human constraint observation is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_human_constraint_observation_no_delete
        BEFORE DELETE ON research_human_constraint_observations BEGIN
            SELECT RAISE(ABORT, 'research human constraint observation is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_side_effect_resolution_no_update
        BEFORE UPDATE ON research_side_effect_resolutions BEGIN
            SELECT RAISE(ABORT, 'research side effect resolution is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_side_effect_resolution_no_delete
        BEFORE DELETE ON research_side_effect_resolutions BEGIN
            SELECT RAISE(ABORT, 'research side effect resolution is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_task_derivation_no_update
        BEFORE UPDATE ON research_task_derivations BEGIN
            SELECT RAISE(ABORT, 'research task derivation is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_task_derivation_no_delete
        BEFORE DELETE ON research_task_derivations BEGIN
            SELECT RAISE(ABORT, 'research task derivation is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_decision_no_update
        BEFORE UPDATE ON research_knowledge_review_decisions BEGIN
            SELECT RAISE(ABORT, 'knowledge review decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_decision_no_delete
        BEFORE DELETE ON research_knowledge_review_decisions BEGIN
            SELECT RAISE(ABORT, 'knowledge review decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_candidate_lineage_no_update
        BEFORE UPDATE ON research_knowledge_candidates
        WHEN NEW.candidate_id IS NOT OLD.candidate_id
          OR NEW.workspace_schema_version IS NOT OLD.workspace_schema_version
          OR NEW.task_id IS NOT OLD.task_id
          OR NEW.goal_id IS NOT OLD.goal_id
          OR NEW.attempt_id IS NOT OLD.attempt_id
          OR NEW.checkpoint_id IS NOT OLD.checkpoint_id
          OR NEW.result_id IS NOT OLD.result_id
          OR NEW.provisional_artifact_id IS NOT OLD.provisional_artifact_id
          OR NEW.source_event_id IS NOT OLD.source_event_id
          OR NEW.source_delta_snapshot_id IS NOT OLD.source_delta_snapshot_id
          OR NEW.candidate_kind IS NOT OLD.candidate_kind
          OR NEW.source_boundary_hash IS NOT OLD.source_boundary_hash
          OR NEW.source_delta_hash IS NOT OLD.source_delta_hash
          OR NEW.source_item_hash IS NOT OLD.source_item_hash
          OR NEW.source_item_index IS NOT OLD.source_item_index
          OR NEW.parent_candidate_id IS NOT OLD.parent_candidate_id
          OR NEW.claim_text IS NOT OLD.claim_text
          OR NEW.citation_ids_json IS NOT OLD.citation_ids_json
          OR NEW.evidence_use_ids_json IS NOT OLD.evidence_use_ids_json
          OR NEW.source_payload_json IS NOT OLD.source_payload_json
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'knowledge candidate lineage is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_candidate_no_delete
        BEFORE DELETE ON research_knowledge_candidates BEGIN
            SELECT RAISE(ABORT, 'knowledge candidate is not deletable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_grounded_fact_no_update
        BEFORE UPDATE ON research_grounded_facts BEGIN
            SELECT RAISE(ABORT, 'grounded fact family is immutable in Stage 1');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_grounded_fact_no_delete
        BEFORE DELETE ON research_grounded_facts BEGIN
            SELECT RAISE(ABORT, 'grounded fact family is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_fact_revision_no_update
        BEFORE UPDATE ON research_fact_revisions BEGIN
            SELECT RAISE(ABORT, 'fact revision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_fact_revision_no_delete
        BEFORE DELETE ON research_fact_revisions BEGIN
            SELECT RAISE(ABORT, 'fact revision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_fact_evidence_link_no_update
        BEFORE UPDATE ON research_fact_evidence_links BEGIN
            SELECT RAISE(ABORT, 'fact evidence link is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_fact_evidence_link_no_delete
        BEFORE DELETE ON research_fact_evidence_links BEGIN
            SELECT RAISE(ABORT, 'fact evidence link is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_artifact_no_update
        BEFORE UPDATE ON research_knowledge_artifacts BEGIN
            SELECT RAISE(ABORT, 'knowledge artifact family is immutable in Stage 1');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_artifact_no_delete
        BEFORE DELETE ON research_knowledge_artifacts BEGIN
            SELECT RAISE(ABORT, 'knowledge artifact family is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_artifact_revision_no_update
        BEFORE UPDATE ON research_knowledge_artifact_revisions BEGIN
            SELECT RAISE(ABORT, 'knowledge artifact revision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_artifact_revision_no_delete
        BEFORE DELETE ON research_knowledge_artifact_revisions BEGIN
            SELECT RAISE(ABORT, 'knowledge artifact revision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_artifact_fact_link_no_update
        BEFORE UPDATE ON research_artifact_fact_links BEGIN
            SELECT RAISE(ABORT, 'artifact fact link is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_artifact_fact_link_no_delete
        BEFORE DELETE ON research_artifact_fact_links BEGIN
            SELECT RAISE(ABORT, 'artifact fact link is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_revision_no_update
        BEFORE UPDATE ON research_topic_page_revisions BEGIN
            SELECT RAISE(ABORT, 'topic page revision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_revision_no_delete
        BEFORE DELETE ON research_topic_page_revisions BEGIN
            SELECT RAISE(ABORT, 'topic page revision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_fact_link_no_update
        BEFORE UPDATE ON research_topic_page_fact_links BEGIN
            SELECT RAISE(ABORT, 'topic page fact link is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_fact_link_no_delete
        BEFORE DELETE ON research_topic_page_fact_links BEGIN
            SELECT RAISE(ABORT, 'topic page fact link is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_review_no_update
        BEFORE UPDATE ON research_topic_page_review_decisions BEGIN
            SELECT RAISE(ABORT, 'topic page review decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_review_no_delete
        BEFORE DELETE ON research_topic_page_review_decisions BEGIN
            SELECT RAISE(ABORT, 'topic page review decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_identity_no_update
        BEFORE UPDATE ON research_topic_pages
        WHEN NEW.page_id IS NOT OLD.page_id
          OR NEW.workspace_schema_version IS NOT OLD.workspace_schema_version
          OR NEW.task_id IS NOT OLD.task_id
          OR NEW.slug IS NOT OLD.slug
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'topic page identity is immutable in Stage 1');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_topic_page_no_delete
        BEFORE DELETE ON research_topic_pages BEGIN
            SELECT RAISE(ABORT, 'topic page is not deletable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_build_identity_no_update
        BEFORE UPDATE ON research_knowledge_build_runs
        WHEN NEW.build_run_id IS NOT OLD.build_run_id
          OR NEW.workspace_schema_version IS NOT OLD.workspace_schema_version
          OR NEW.task_id IS NOT OLD.task_id
          OR NEW.build_kind IS NOT OLD.build_kind
          OR NEW.command_id IS NOT OLD.command_id
          OR NEW.input_hash IS NOT OLD.input_hash
          OR NEW.input_json IS NOT OLD.input_json
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'knowledge BuildRun identity is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_build_no_delete
        BEFORE DELETE ON research_knowledge_build_runs BEGIN
            SELECT RAISE(ABORT, 'knowledge BuildRun is not deletable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_revalidation_no_update
        BEFORE UPDATE ON research_knowledge_revalidation_observations BEGIN
            SELECT RAISE(ABORT, 'knowledge revalidation observation is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_revalidation_no_delete
        BEFORE DELETE ON research_knowledge_revalidation_observations BEGIN
            SELECT RAISE(ABORT, 'knowledge revalidation observation is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_fact_state_identity_no_update
        BEFORE UPDATE ON research_knowledge_fact_states
        WHEN NEW.fact_id IS NOT OLD.fact_id OR NEW.task_id IS NOT OLD.task_id
        BEGIN
            SELECT RAISE(ABORT, 'knowledge Fact state identity is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_fact_state_no_delete
        BEFORE DELETE ON research_knowledge_fact_states BEGIN
            SELECT RAISE(ABORT, 'knowledge Fact state is not deletable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_update_candidate_lineage_no_update
        BEFORE UPDATE ON research_knowledge_update_candidates
        WHEN NEW.update_candidate_id IS NOT OLD.update_candidate_id
          OR NEW.task_id IS NOT OLD.task_id
          OR NEW.fact_id IS NOT OLD.fact_id
          OR NEW.source_fact_revision_id IS NOT OLD.source_fact_revision_id
          OR NEW.related_fact_revision_id IS NOT OLD.related_fact_revision_id
          OR NEW.source_observation_set_id IS NOT OLD.source_observation_set_id
          OR NEW.candidate_kind IS NOT OLD.candidate_kind
          OR NEW.proposed_claim IS NOT OLD.proposed_claim
          OR NEW.temporal_scope_json IS NOT OLD.temporal_scope_json
          OR NEW.viewpoint_scope_json IS NOT OLD.viewpoint_scope_json
          OR NEW.evidence_use_ids_json IS NOT OLD.evidence_use_ids_json
          OR NEW.affected_artifact_ids_json IS NOT OLD.affected_artifact_ids_json
          OR NEW.affected_page_ids_json IS NOT OLD.affected_page_ids_json
          OR NEW.validator_status IS NOT OLD.validator_status
          OR NEW.parent_candidate_id IS NOT OLD.parent_candidate_id
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'knowledge update Candidate lineage is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_update_candidate_no_delete
        BEFORE DELETE ON research_knowledge_update_candidates BEGIN
            SELECT RAISE(ABORT, 'knowledge update Candidate is not deletable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_operation_identity_no_update
        BEFORE UPDATE ON research_knowledge_update_operations
        WHEN NEW.operation_id IS NOT OLD.operation_id
          OR NEW.task_id IS NOT OLD.task_id
          OR NEW.operation_kind IS NOT OLD.operation_kind
          OR NEW.target_reference IS NOT OLD.target_reference
          OR NEW.dedup_key IS NOT OLD.dedup_key
          OR NEW.command_id IS NOT OLD.command_id
          OR NEW.input_hash IS NOT OLD.input_hash
          OR NEW.input_json IS NOT OLD.input_json
          OR NEW.expected_heads_json IS NOT OLD.expected_heads_json
          OR NEW.max_attempts IS NOT OLD.max_attempts
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'knowledge operation identity is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_operation_no_delete
        BEFORE DELETE ON research_knowledge_update_operations BEGIN
            SELECT RAISE(ABORT, 'knowledge operation is not deletable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_lifecycle_decision_no_update
        BEFORE UPDATE ON research_knowledge_lifecycle_decisions BEGIN
            SELECT RAISE(ABORT, 'knowledge lifecycle decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_lifecycle_decision_no_delete
        BEFORE DELETE ON research_knowledge_lifecycle_decisions BEGIN
            SELECT RAISE(ABORT, 'knowledge lifecycle decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_conflict_no_update
        BEFORE UPDATE ON research_knowledge_conflict_observations BEGIN
            SELECT RAISE(ABORT, 'knowledge conflict observation is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_conflict_no_delete
        BEFORE DELETE ON research_knowledge_conflict_observations BEGIN
            SELECT RAISE(ABORT, 'knowledge conflict observation is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_page_revision_decision_no_update
        BEFORE UPDATE ON research_topic_page_revision_decisions BEGIN
            SELECT RAISE(ABORT, 'topic page revision decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_page_revision_decision_no_delete
        BEFORE DELETE ON research_topic_page_revision_decisions BEGIN
            SELECT RAISE(ABORT, 'topic page revision decision is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_export_no_update
        BEFORE UPDATE ON research_knowledge_exports BEGIN
            SELECT RAISE(ABORT, 'knowledge export record is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_knowledge_export_no_delete
        BEFORE DELETE ON research_knowledge_exports BEGIN
            SELECT RAISE(ABORT, 'knowledge export record is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_candidate_delta_event_no_update
        BEFORE UPDATE ON research_events
        WHEN OLD.event_type='candidate_deltas_materialized'
          OR NEW.event_type='candidate_deltas_materialized'
        BEGIN
            SELECT RAISE(ABORT, 'candidate delta event is immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_research_candidate_delta_event_no_delete
        BEFORE DELETE ON research_events
        WHEN OLD.event_type='candidate_deltas_materialized'
        BEGIN
            SELECT RAISE(ABORT, 'candidate delta event is immutable');
        END;
        """
    )
