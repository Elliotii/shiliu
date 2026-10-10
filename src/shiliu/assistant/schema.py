from __future__ import annotations

import sqlite3


def initialize_assistant_foundation_schema(connection: sqlite3.Connection) -> None:
    """Create only the Stage-A source/scope tables required by later phases."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assistant_spaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            principal_id TEXT NOT NULL,
            name TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '',
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            video_ids_json TEXT NOT NULL DEFAULT '[]',
            all_active INTEGER NOT NULL DEFAULT 0,
            maintenance_mode TEXT NOT NULL DEFAULT 'on_demand'
                CHECK(maintenance_mode IN ('on_demand', 'automatic')),
            scope_version INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(principal_id, name)
        );

        CREATE TABLE IF NOT EXISTS assistant_source_heads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            principal_id TEXT NOT NULL,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            metadata_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            membership_hash TEXT NOT NULL,
            current_revision TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(principal_id, video_id)
        );

        CREATE TABLE IF NOT EXISTS assistant_source_revisions (
            revision TEXT PRIMARY KEY,
            head_id INTEGER NOT NULL REFERENCES assistant_source_heads(id) ON DELETE CASCADE,
            metadata_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            membership_hash TEXT NOT NULL,
            snapshot_ref TEXT NOT NULL,
            coverage TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_assistant_source_revisions_head
            ON assistant_source_revisions(head_id, created_at DESC);
        """
    )
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(assistant_spaces)").fetchall()
    }
    if "video_ids_json" not in existing:
        connection.execute(
            "ALTER TABLE assistant_spaces ADD COLUMN video_ids_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "maintenance_mode" not in existing:
        # Existing spaces keep their previous event behavior. New spaces default
        # to on-demand maintenance, independently of their search scope.
        connection.execute(
            "ALTER TABLE assistant_spaces ADD COLUMN maintenance_mode TEXT NOT NULL DEFAULT 'automatic'"
        )


def initialize_assistant_runtime_schema(connection: sqlite3.Connection) -> None:
    """Create the Stage-B authoritative run, memory, and durable-job tables."""
    initialize_assistant_foundation_schema(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assistant_threads (
            id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            space_id INTEGER NOT NULL REFERENCES assistant_spaces(id) ON DELETE RESTRICT,
            title TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_runs (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL,
            status TEXT NOT NULL,
            run_epoch INTEGER NOT NULL DEFAULT 1,
            step_count INTEGER NOT NULL DEFAULT 0,
            tool_count INTEGER NOT NULL DEFAULT 0,
            working_state_json TEXT NOT NULL DEFAULT '{}',
            usage_json TEXT NOT NULL DEFAULT '{}',
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            memory_epoch INTEGER NOT NULL DEFAULT 0,
            extraction_memory_epoch INTEGER NOT NULL DEFAULT 0,
            observed_memory_epoch INTEGER NOT NULL DEFAULT 0,
            last_error_code TEXT,
            last_error_message TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(thread_id, request_id)
        );

        CREATE TABLE IF NOT EXISTS assistant_messages (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
            run_id TEXT REFERENCES assistant_runs(id) ON DELETE SET NULL,
            seq INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            provider_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(thread_id, seq)
        );

        CREATE TABLE IF NOT EXISTS assistant_tool_calls (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES assistant_runs(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            call_id TEXT NOT NULL,
            name TEXT NOT NULL,
            args_json TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            operation_key TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(run_id, ordinal),
            UNIQUE(run_id, call_id)
        );

        CREATE TABLE IF NOT EXISTS assistant_run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES assistant_runs(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(run_id, seq)
        );

        CREATE TABLE IF NOT EXISTS assistant_memories (
            id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            scope_kind TEXT NOT NULL CHECK(scope_kind IN ('user', 'space')),
            scope_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL CHECK(kind IN ('preference', 'constraint', 'decision', 'context')),
            text TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            origin TEXT NOT NULL CHECK(origin IN ('explicit', 'extracted')),
            source_message_ids_json TEXT NOT NULL DEFAULT '[]',
            source_excerpt TEXT NOT NULL DEFAULT '',
            valid_from TEXT,
            expires_at TEXT,
            validity_note TEXT NOT NULL DEFAULT '',
            validity_timezone TEXT,
            status TEXT NOT NULL CHECK(status IN ('active', 'needs_review', 'superseded', 'forgotten')),
            version INTEGER NOT NULL DEFAULT 1,
            pinned INTEGER NOT NULL DEFAULT 0,
            user_edited INTEGER NOT NULL DEFAULT 0,
            supersedes_id TEXT REFERENCES assistant_memories(id) ON DELETE SET NULL,
            last_projected_version INTEGER,
            backend_id TEXT,
            change_epoch INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_memory_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL REFERENCES assistant_memories(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            operation TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            reason TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL,
            memory_epoch INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(memory_id, version)
        );

        CREATE TABLE IF NOT EXISTS assistant_memory_suppressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            principal_id TEXT NOT NULL,
            scope_kind TEXT NOT NULL,
            scope_id TEXT NOT NULL DEFAULT '',
            subject_key TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            source_message_ids_json TEXT NOT NULL DEFAULT '[]',
            memory_epoch INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(principal_id, scope_kind, scope_id, subject_key, content_hash)
        );

        CREATE TABLE IF NOT EXISTS assistant_jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            cursor TEXT,
            attempt INTEGER NOT NULL DEFAULT 0,
            not_before TEXT NOT NULL,
            lease_owner TEXT,
            lease_until TEXT,
            lease_epoch INTEGER NOT NULL DEFAULT 0,
            proposal_json TEXT,
            last_error_code TEXT,
            last_error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS assistant_mutation_receipts (
            operation_key TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_runtime_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        INSERT OR IGNORE INTO assistant_runtime_state(key, value, updated_at)
        VALUES('memory_epoch', '0', CURRENT_TIMESTAMP);

        CREATE TABLE IF NOT EXISTS assistant_task_notes (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
            task_segment INTEGER NOT NULL DEFAULT 1,
            note_version INTEGER NOT NULL DEFAULT 1,
            covered_until_message_seq INTEGER NOT NULL DEFAULT 0,
            source_run_ids_json TEXT NOT NULL DEFAULT '[]',
            goal TEXT NOT NULL DEFAULT '',
            explicit_constraints_json TEXT NOT NULL DEFAULT '[]',
            searched_scope_and_material_refs_json TEXT NOT NULL DEFAULT '[]',
            findings_json TEXT NOT NULL DEFAULT '[]',
            open_questions_json TEXT NOT NULL DEFAULT '[]',
            next_actions_json TEXT NOT NULL DEFAULT '[]',
            dependencies_json TEXT NOT NULL DEFAULT '[]',
            scope_version INTEGER NOT NULL,
            memory_generation INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(thread_id, task_segment)
        );

        CREATE TABLE IF NOT EXISTS assistant_model_budget_days (
            budget_date TEXT NOT NULL,
            lane TEXT NOT NULL,
            request_limit INTEGER NOT NULL,
            requests_used INTEGER NOT NULL DEFAULT 0,
            usage_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            PRIMARY KEY(budget_date, lane)
        );

        CREATE TABLE IF NOT EXISTS assistant_scheduler_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            queue_wait_seconds REAL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_assistant_threads_space
            ON assistant_threads(principal_id, space_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assistant_runs_status
            ON assistant_runs(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_assistant_messages_thread
            ON assistant_messages(thread_id, seq);
        CREATE INDEX IF NOT EXISTS idx_assistant_memories_scope
            ON assistant_memories(principal_id, scope_kind, scope_id, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assistant_jobs_due
            ON assistant_jobs(status, not_before, created_at);
        CREATE INDEX IF NOT EXISTS idx_assistant_task_notes_thread
            ON assistant_task_notes(thread_id, task_segment, note_version);
        CREATE INDEX IF NOT EXISTS idx_assistant_scheduler_job
            ON assistant_scheduler_events(job_id, id);
        """
    )
    run_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(assistant_runs)").fetchall()
    }
    for name in ("extraction_memory_epoch", "observed_memory_epoch"):
        if name not in run_columns:
            connection.execute(
                f"ALTER TABLE assistant_runs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                f"UPDATE assistant_runs SET {name}=memory_epoch WHERE {name}=0"
            )
    memory_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(assistant_memories)").fetchall()
    }
    for name, definition in {
        "validity_note": "TEXT NOT NULL DEFAULT ''",
        "validity_timezone": "TEXT",
        "change_epoch": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if name not in memory_columns:
            connection.execute(f"ALTER TABLE assistant_memories ADD COLUMN {name} {definition}")
    change_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(assistant_memory_changes)").fetchall()
    }
    if "memory_epoch" not in change_columns:
        connection.execute(
            "ALTER TABLE assistant_memory_changes ADD COLUMN memory_epoch INTEGER NOT NULL DEFAULT 0"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_assistant_memory_changes_epoch "
        "ON assistant_memory_changes(memory_epoch, id)"
    )
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS assistant_memories_fts
            USING fts5(memory_id UNINDEXED, text, tokenize='trigram')
            """
        )
    except sqlite3.OperationalError:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS assistant_memories_fts
            USING fts5(memory_id UNINDEXED, text)
            """
        )
    initialize_assistant_wiki_schema(connection)


def initialize_assistant_wiki_schema(connection: sqlite3.Connection) -> None:
    """Create Stage-C source-card and versioned Wiki storage."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assistant_source_dirty (
            video_id INTEGER PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
            dirty_generation INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_maintenance_batches (
            id TEXT PRIMARY KEY,
            space_id INTEGER NOT NULL REFERENCES assistant_spaces(id),
            source_limit INTEGER NOT NULL CHECK(source_limit BETWEEN 1 AND 10),
            model_limit INTEGER NOT NULL CHECK(model_limit BETWEEN 1 AND 30),
            calls_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_source_cards (
            revision TEXT PRIMARY KEY REFERENCES assistant_source_revisions(revision) ON DELETE CASCADE,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            input_hash TEXT NOT NULL,
            card_json TEXT NOT NULL,
            coverage TEXT NOT NULL,
            extraction_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_source_card_batches (
            revision TEXT NOT NULL REFERENCES assistant_source_revisions(revision) ON DELETE CASCADE,
            batch_index INTEGER NOT NULL,
            input_hash TEXT NOT NULL,
            card_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(revision, batch_index)
        );
        CREATE INDEX IF NOT EXISTS idx_assistant_source_cards_input
            ON assistant_source_cards(video_id, input_hash, updated_at DESC);

        CREATE TABLE IF NOT EXISTS assistant_wiki_pages (
            id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            space_id INTEGER NOT NULL REFERENCES assistant_spaces(id) ON DELETE CASCADE,
            normalized_title TEXT NOT NULL,
            title TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            page_type TEXT NOT NULL CHECK(page_type IN ('concept','method','comparison','topic')),
            summary TEXT NOT NULL DEFAULT '',
            blocks_json TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            scope_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(principal_id, space_id, normalized_title)
        );
        CREATE INDEX IF NOT EXISTS idx_assistant_wiki_pages_space
            ON assistant_wiki_pages(principal_id, space_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS assistant_wiki_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            block_id TEXT NOT NULL,
            source_revision TEXT NOT NULL REFERENCES assistant_source_revisions(revision) ON DELETE RESTRICT,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            dependency_kind TEXT NOT NULL DEFAULT 'source',
            created_at TEXT NOT NULL,
            UNIQUE(page_id, block_id, source_revision)
        );
        CREATE INDEX IF NOT EXISTS idx_assistant_wiki_dependencies_page
            ON assistant_wiki_dependencies(page_id, block_id);

        CREATE TABLE IF NOT EXISTS assistant_wiki_materials (
            page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            source_revision TEXT NOT NULL REFERENCES assistant_source_revisions(revision),
            relation TEXT NOT NULL CHECK(relation IN ('supports_block','associated')),
            status TEXT NOT NULL DEFAULT 'integrated',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(page_id, video_id)
        );
        CREATE INDEX IF NOT EXISTS idx_assistant_wiki_materials_video
            ON assistant_wiki_materials(video_id, page_id);

        CREATE TABLE IF NOT EXISTS assistant_wiki_personal_dependencies (
            page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            block_id TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            memory_version INTEGER NOT NULL,
            source_message_id TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(page_id, block_id)
        );

        CREATE TABLE IF NOT EXISTS assistant_wiki_redirects (
            old_page_id TEXT PRIMARY KEY REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            target_page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            space_id INTEGER NOT NULL REFERENCES assistant_spaces(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assistant_wiki_proposals (
            id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            space_id INTEGER NOT NULL REFERENCES assistant_spaces(id),
            kind TEXT NOT NULL,
            source_page_id TEXT REFERENCES assistant_wiki_pages(id),
            target_page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id),
            source_version INTEGER,
            target_version INTEGER NOT NULL,
            input_fingerprint TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected','stale')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(principal_id, space_id, kind, target_page_id, input_fingerprint)
        );

        CREATE TABLE IF NOT EXISTS assistant_knowledge_plans (
            id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            space_id INTEGER NOT NULL REFERENCES assistant_spaces(id),
            version INTEGER NOT NULL DEFAULT 1,
            scope_version INTEGER NOT NULL,
            source_message_id TEXT,
            payload_json TEXT NOT NULL,
            results_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL CHECK(status IN ('pending','partial','completed','rejected')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assistant_knowledge_plans_space
            ON assistant_knowledge_plans(principal_id,space_id,created_at DESC);

        CREATE TABLE IF NOT EXISTS assistant_wiki_operation_states (
            page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            PRIMARY KEY(page_id,version)
        );

        CREATE TABLE IF NOT EXISTS assistant_wiki_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id TEXT NOT NULL REFERENCES assistant_wiki_pages(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            operation TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(page_id, version)
        );
        """
    )
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS assistant_wiki_fts
            USING fts5(page_id UNINDEXED, title, aliases, summary, blocks, tokenize='trigram')
            """
        )
    except sqlite3.OperationalError:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS assistant_wiki_fts
            USING fts5(page_id UNINDEXED, title, aliases, summary, blocks)
            """
        )
