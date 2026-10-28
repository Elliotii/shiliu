"""Terminal cycle must include independent derivation's deferred lineage edge."""

from contextlib import closing
import json
import sqlite3
from poc_source import make_source
from schema_support import formal_target
from test_etl import target_etl
from shiliu.config import load_postgres_config
from shiliu.migration.etl import import_snapshot


def test_terminal_independent_child_import_keeps_derivation_in_atomic_cycle():
    source = make_source()
    with closing(sqlite3.connect(source)) as c, c:
        c.row_factory = sqlite3.Row
        task = dict(c.execute("SELECT * FROM research_tasks").fetchone())
        goal = dict(c.execute("SELECT * FROM research_goals").fetchone())
        attempt = dict(c.execute("SELECT * FROM research_attempts").fetchone())
        checkpoint = dict(c.execute("SELECT * FROM research_checkpoints").fetchone())

        def put(name, row):
            c.execute(
                "INSERT INTO "
                + name
                + " ("
                + ",".join('"' + k + '"' for k in row)
                + ") VALUES ("
                + ",".join("?" for _ in row)
                + ")",
                list(row.values()),
            )

        put(
            "research_tasks",
            dict(
                task,
                task_id="synthetic_independent",
                parent_task_id=None,
                status="terminal",
                active_goal_id="synthetic_child_goal",
                terminal_result_id="synthetic_child_result",
            ),
        )
        put(
            "research_goals",
            dict(
                goal,
                goal_id="synthetic_child_goal",
                task_id="synthetic_independent",
                parent_goal_id=None,
                created_by_event_id=None,
            ),
        )
        put(
            "research_attempts",
            dict(
                attempt,
                attempt_id="synthetic_child_attempt",
                task_id="synthetic_independent",
                goal_id="synthetic_child_goal",
                cause="branch",
                parent_attempt_id=attempt["attempt_id"],
                source_checkpoint_id=checkpoint["checkpoint_id"],
                status="terminal",
                result_id="synthetic_child_result",
            ),
        )
        put(
            "research_checkpoints",
            dict(
                checkpoint,
                checkpoint_id="synthetic_child_checkpoint",
                task_id="synthetic_independent",
                goal_id="synthetic_child_goal",
                attempt_id="synthetic_child_attempt",
                parent_checkpoint_id=None,
            ),
        )
        c.execute(
            "INSERT INTO research_results (result_id,task_id,goal_id,attempt_id,checkpoint_id,answer_status,termination_reason,failure_class,reason_detail,is_task_terminal,owner_epoch,created_at) VALUES ('synthetic_child_result','synthetic_independent','synthetic_child_goal','synthetic_child_attempt','synthetic_child_checkpoint','not_produced','cancelled','none','synthetic history',1,7,'2026-10-23T00:00:00+00:00')"
        )
        put(
            "research_task_derivations",
            dict(
                derivation_id="synthetic_derivation",
                derivation_schema_version="research-task-derivation-v1",
                source_task_id=task["task_id"],
                source_goal_id=goal["goal_id"],
                source_attempt_id=attempt["attempt_id"],
                source_checkpoint_id=checkpoint["checkpoint_id"],
                child_task_id="synthetic_independent",
                child_goal_id="synthetic_child_goal",
                child_attempt_id="synthetic_child_attempt",
                command_id="synthetic-derive",
                derivation_kind="branch",
                source_state_hash=checkpoint["state_hash"],
                source_manifest_json=json.dumps({}),
                goal_delta_json=json.dumps({}),
                payload_hash="synthetic",
                principal_id="local_operator",
                created_at=task["created_at"],
            ),
        )
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        report = import_snapshot(source, target, "w14_derivation_cycle")
        assert report["counts"]["research_tasks"] == 2
        assert report["counts"]["research_task_derivations"] == 1
        assert import_snapshot(source, target, "w14_derivation_cycle") == report
