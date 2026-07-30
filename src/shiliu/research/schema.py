from __future__ import annotations

import sqlite3


RESEARCH_STATE_SCHEMA_VERSION = "v5-a-stage1-state-v1"
INNER_RESEARCH_STATE_SCHEMA_VERSION = "v5-a-stage2-inner-state-v1"
INNER_ACTION_SCHEMA_VERSION = "v5-a-stage2-action-v1"
EVIDENCE_USE_SCHEMA_VERSION = "v5-a-stage2-evidence-use-v1"
EVIDENCE_VALIDATION_POLICY_VERSION = "v5-a-stage2-currentness-v1"
PROVISIONAL_ARTIFACT_SCHEMA_VERSION = "v5-a-stage2-provisional-artifact-v1"


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
                    'provider_error', 'implementation_error'
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
        """
    )
