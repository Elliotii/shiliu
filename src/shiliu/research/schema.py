from __future__ import annotations

import sqlite3


RESEARCH_STATE_SCHEMA_VERSION = "v5-a-stage1-state-v1"


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
        """
    )
