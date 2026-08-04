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
KNOWLEDGE_WORKSPACE_SCHEMA_VERSION = "v5-b-stage1-knowledge-workspace-v1"
KNOWLEDGE_VALIDATION_POLICY_VERSION = "v5-b-stage1-current-evidence-v1"
KNOWLEDGE_ARTIFACT_POLICY_VERSION = "v5-b-stage1-artifact-build-v1"
TOPIC_PAGE_POLICY_VERSION = "v5-b-stage1-topic-page-build-v1"


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
            current_version INTEGER NOT NULL CHECK(current_version = 1),
            review_status TEXT NOT NULL CHECK(review_status IN ('draft', 'published', 'returned')),
            state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_topic_page_revisions (
            page_revision_id TEXT PRIMARY KEY,
            page_id TEXT NOT NULL REFERENCES research_topic_pages(page_id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES research_tasks(task_id) ON DELETE RESTRICT,
            version INTEGER NOT NULL CHECK(version = 1),
            parent_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
            supersedes_revision_id TEXT REFERENCES research_topic_page_revisions(page_revision_id) ON DELETE RESTRICT,
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
            expected_version INTEGER NOT NULL CHECK(expected_version = 1),
            command_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, command_id),
            UNIQUE(page_id)
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
          OR NEW.current_version IS NOT OLD.current_version
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
