CREATE TABLE shiliu."ask_events" (
    "run_id" text NOT NULL,
    "sequence" bigint NOT NULL,
    "event_type" text NOT NULL,
    "payload_json" jsonb NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("run_id","sequence"),
    CHECK (sequence >= 0)
);

CREATE TABLE shiliu."ask_runs" (
    "run_id" text NOT NULL,
    "run_schema_version" text NOT NULL,
    "parent_run_id" text,
    "created_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    "query" text NOT NULL,
    "mode" text NOT NULL,
    "filters_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "lifecycle_status" text NOT NULL,
    "answer_status" text,
    "termination_reason" text,
    "query_analysis_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "rewrites_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "final_evidence_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "citations_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "answer_blocks_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "limitations_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "usage_summary_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "trace_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "error_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "workspace_id" text NOT NULL,
    "owner_user_id" text NOT NULL,
    PRIMARY KEY ("run_id"),
    UNIQUE ("workspace_id","run_id"),
    CHECK (mode IN ('fast', 'deep')),
    CHECK (lifecycle_status IN ('running', 'completed', 'failed')),
    CHECK (answer_status IS NULL OR answer_status IN ('complete', 'partial', 'insufficient'))
);

CREATE INDEX "idx_ask_runs_created" ON shiliu."ask_runs" ("workspace_id", "created_at" DESC, "run_id");

CREATE INDEX "idx_ask_runs_parent" ON shiliu."ask_runs" ("workspace_id", "parent_run_id", "created_at");

CREATE TABLE shiliu."ask_search_trace_links" (
    "run_id" text NOT NULL,
    "sequence" bigint NOT NULL,
    "relation_kind" text NOT NULL,
    "decision_sequence" bigint,
    "execution_id" text,
    "search_trace_id" text NOT NULL,
    "trace_persisted" boolean NOT NULL,
    "trace_error" text,
    "query" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("run_id","sequence"),
    CHECK (sequence >= 0),
    CHECK (trace_persisted IN (false,true))
);

CREATE INDEX "idx_ask_search_trace" ON shiliu."ask_search_trace_links" ("workspace_id", "search_trace_id", "run_id");

CREATE TABLE shiliu."assistant_jobs" (
    "id" text NOT NULL,
    "kind" text NOT NULL,
    "dedupe_key" text NOT NULL,
    "status" text NOT NULL,
    "payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "cursor" text,
    "attempt" bigint NOT NULL DEFAULT 0,
    "not_before" timestamptz NOT NULL,
    "lease_owner" text,
    "lease_until" timestamptz,
    "lease_epoch" bigint NOT NULL DEFAULT 0,
    "proposal_json" jsonb,
    "last_error_code" text,
    "last_error_message" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    "workspace_id" text NOT NULL,
    "principal_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("workspace_id","principal_id","dedupe_key"),
    UNIQUE ("workspace_id","id"),
    UNIQUE ("workspace_id","principal_id","id")
);

CREATE INDEX "idx_assistant_jobs_due" ON shiliu."assistant_jobs" ("workspace_id", "status", "not_before", "created_at");

CREATE TABLE shiliu."assistant_knowledge_plans" (
    "id" text NOT NULL,
    "principal_id" text NOT NULL,
    "space_id" bigint NOT NULL,
    "version" bigint NOT NULL DEFAULT 1,
    "scope_version" bigint NOT NULL,
    "source_message_id" text,
    "payload_json" jsonb NOT NULL,
    "results_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "status" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    CHECK (status IN ('pending','partial','completed','rejected'))
);

CREATE INDEX "idx_assistant_knowledge_plans_space" ON shiliu."assistant_knowledge_plans" ("workspace_id", "principal_id", "space_id", "created_at" DESC);

CREATE TABLE shiliu."assistant_maintenance_batches" (
    "id" text NOT NULL,
    "space_id" bigint NOT NULL,
    "source_limit" bigint NOT NULL,
    "model_limit" bigint NOT NULL,
    "calls_used" bigint NOT NULL DEFAULT 0,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    CHECK (source_limit BETWEEN 1 AND 10),
    CHECK (model_limit BETWEEN 1 AND 30)
);

CREATE TABLE shiliu."assistant_memories" (
    "id" text NOT NULL,
    "principal_id" text NOT NULL,
    "scope_kind" text NOT NULL,
    "scope_id" text NOT NULL DEFAULT '',
    "kind" text NOT NULL,
    "text" text NOT NULL,
    "subject_key" text NOT NULL,
    "origin" text NOT NULL,
    "source_message_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "source_excerpt" text NOT NULL DEFAULT '',
    "valid_from" timestamptz,
    "expires_at" timestamptz,
    "validity_note" text NOT NULL DEFAULT '',
    "validity_timezone" text,
    "time_context_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "status" text NOT NULL,
    "version" bigint NOT NULL DEFAULT 1,
    "pinned" boolean NOT NULL DEFAULT false,
    "user_edited" boolean NOT NULL DEFAULT false,
    "supersedes_id" text,
    "last_projected_version" bigint,
    "change_epoch" bigint NOT NULL DEFAULT 0,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "scope_space_id" bigint,
    "tokenized_text" text NOT NULL DEFAULT '',
    "search_vector" tsvector NOT NULL DEFAULT ''::tsvector,
    PRIMARY KEY ("id"),
    UNIQUE ("workspace_id","id"),
    CHECK (scope_kind IN ('user', 'space')),
    CHECK (kind IN ('preference', 'constraint', 'decision', 'context')),
    CHECK (origin IN ('explicit', 'extracted')),
    CHECK (status IN ('active', 'needs_review', 'superseded', 'forgotten')),
    CHECK ((scope_kind='user' AND scope_id='' AND scope_space_id IS NULL) OR (scope_kind='space' AND scope_space_id IS NOT NULL AND scope_id=scope_space_id::text))
);

CREATE INDEX "idx_assistant_memories_scope" ON shiliu."assistant_memories" ("workspace_id", "principal_id", "scope_kind", "scope_id", "status", "updated_at" DESC);

CREATE INDEX "assistant_memories_fts_gin" ON shiliu."assistant_memories" USING GIN(search_vector);

CREATE TABLE shiliu."assistant_memory_changes" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "memory_id" text NOT NULL,
    "version" bigint NOT NULL,
    "operation" text NOT NULL,
    "before_json" jsonb,
    "after_json" jsonb,
    "reason" text NOT NULL DEFAULT '',
    "actor" text NOT NULL,
    "memory_epoch" bigint NOT NULL DEFAULT 0,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("memory_id","version")
);

CREATE INDEX "idx_assistant_memory_changes_epoch" ON shiliu."assistant_memory_changes" ("workspace_id", "memory_epoch", "id");

CREATE TABLE shiliu."assistant_memory_suppressions" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "principal_id" text NOT NULL,
    "scope_kind" text NOT NULL,
    "scope_id" text NOT NULL DEFAULT '',
    "subject_key" text NOT NULL,
    "content_hash" text NOT NULL,
    "source_message_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "memory_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("principal_id","scope_kind","scope_id","subject_key","content_hash")
);

CREATE TABLE shiliu."assistant_messages" (
    "id" text NOT NULL,
    "thread_id" text NOT NULL,
    "run_id" text,
    "seq" bigint NOT NULL,
    "role" text NOT NULL,
    "content" text NOT NULL DEFAULT '',
    "provider_payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("thread_id","seq"),
    UNIQUE ("workspace_id","id")
);

CREATE INDEX "idx_assistant_messages_thread" ON shiliu."assistant_messages" ("workspace_id", "thread_id", "seq");

CREATE TABLE shiliu."assistant_model_budget_days" (
    "budget_date" date NOT NULL,
    "lane" text NOT NULL,
    "request_limit" bigint NOT NULL,
    "requests_used" bigint NOT NULL DEFAULT 0,
    "usage_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "principal_id" text NOT NULL,
    PRIMARY KEY ("workspace_id","principal_id","budget_date","lane")
);

CREATE TABLE shiliu."assistant_mutation_receipts" (
    "operation_key" text NOT NULL,
    "principal_id" text NOT NULL,
    "operation" text NOT NULL,
    "result_json" jsonb NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("workspace_id","principal_id","operation_key")
);

CREATE TABLE shiliu."assistant_run_events" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "run_id" text NOT NULL,
    "seq" bigint NOT NULL,
    "event_type" text NOT NULL,
    "payload_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("run_id","seq")
);

CREATE TABLE shiliu."assistant_runs" (
    "id" text NOT NULL,
    "thread_id" text NOT NULL,
    "request_id" text NOT NULL,
    "status" text NOT NULL,
    "run_epoch" bigint NOT NULL DEFAULT 1,
    "step_count" bigint NOT NULL DEFAULT 0,
    "tool_count" bigint NOT NULL DEFAULT 0,
    "working_state_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "usage_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "cancel_requested" boolean NOT NULL DEFAULT false,
    "memory_epoch" bigint NOT NULL DEFAULT 0,
    "extraction_memory_epoch" bigint NOT NULL DEFAULT 0,
    "observed_memory_epoch" bigint NOT NULL DEFAULT 0,
    "last_error_code" text,
    "last_error_message" text,
    "created_at" timestamptz NOT NULL,
    "started_at" timestamptz,
    "updated_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    "workspace_id" text NOT NULL,
    "insertion_seq" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("thread_id","request_id"),
    UNIQUE ("workspace_id","insertion_seq"),
    UNIQUE ("workspace_id","id"),
    UNIQUE ("workspace_id","thread_id","id")
);

CREATE INDEX "idx_assistant_runs_status" ON shiliu."assistant_runs" ("workspace_id", "status", "updated_at");

CREATE TABLE shiliu."assistant_runtime_state" (
    "key" text NOT NULL,
    "value" text NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "embedding_domain" text,
    "embedding_profile_id" text,
    PRIMARY KEY ("workspace_id","principal_id","key"),
    UNIQUE ("workspace_id","principal_id","embedding_domain"),
    CHECK ((embedding_domain IS NULL AND embedding_profile_id IS NULL) OR (embedding_domain IS NOT NULL AND embedding_domain IN ('collection','wiki','memory') AND embedding_profile_id IS NOT NULL))
);

CREATE TABLE shiliu."assistant_scheduler_events" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "job_id" text NOT NULL,
    "event_type" text NOT NULL,
    "reason" text NOT NULL DEFAULT '',
    "queue_wait_seconds" double precision,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "principal_id" text NOT NULL,
    PRIMARY KEY ("id")
);

CREATE INDEX "idx_assistant_scheduler_job" ON shiliu."assistant_scheduler_events" ("workspace_id", "job_id", "id");

CREATE TABLE shiliu."assistant_source_card_batches" (
    "revision" text NOT NULL,
    "batch_index" bigint NOT NULL,
    "input_hash" text NOT NULL,
    "card_json" jsonb NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("revision","batch_index")
);

CREATE TABLE shiliu."assistant_source_cards" (
    "revision" text NOT NULL,
    "video_id" bigint NOT NULL,
    "input_hash" text NOT NULL,
    "card_json" jsonb NOT NULL,
    "coverage" text NOT NULL,
    "extraction_version" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("revision")
);

CREATE INDEX "idx_assistant_source_cards_input" ON shiliu."assistant_source_cards" ("workspace_id", "video_id", "input_hash", "updated_at" DESC);

CREATE TABLE shiliu."assistant_source_dirty" (
    "video_id" bigint NOT NULL,
    "dirty_generation" bigint NOT NULL DEFAULT 0,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("video_id")
);

CREATE TABLE shiliu."assistant_source_heads" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "principal_id" text NOT NULL,
    "video_id" bigint NOT NULL,
    "metadata_hash" text NOT NULL,
    "content_hash" text NOT NULL,
    "membership_hash" text NOT NULL,
    "current_revision" text,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("principal_id","video_id"),
    UNIQUE ("workspace_id","id"),
    UNIQUE ("workspace_id","video_id","id")
);

CREATE TABLE shiliu."assistant_source_revisions" (
    "revision" text NOT NULL,
    "head_id" bigint NOT NULL,
    "metadata_hash" text NOT NULL,
    "content_hash" text NOT NULL,
    "membership_hash" text NOT NULL,
    "snapshot_ref" text NOT NULL,
    "coverage" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "video_id" bigint NOT NULL,
    PRIMARY KEY ("revision"),
    UNIQUE ("workspace_id","revision"),
    UNIQUE ("workspace_id","head_id","revision"),
    UNIQUE ("workspace_id","video_id","revision")
);

CREATE INDEX "idx_assistant_source_revisions_head" ON shiliu."assistant_source_revisions" ("workspace_id", "head_id", "created_at" DESC);

CREATE TABLE shiliu."assistant_spaces" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "principal_id" text NOT NULL,
    "name" text NOT NULL,
    "goal" text NOT NULL DEFAULT '',
    "source_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "video_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "all_active" boolean NOT NULL DEFAULT false,
    "maintenance_mode" text NOT NULL DEFAULT 'on_demand',
    "scope_version" bigint NOT NULL DEFAULT 1,
    "enabled" boolean NOT NULL DEFAULT true,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("principal_id","name"),
    UNIQUE ("workspace_id","principal_id","id"),
    UNIQUE ("workspace_id","id"),
    CHECK (maintenance_mode IN ('on_demand', 'automatic'))
);

CREATE TABLE shiliu."assistant_task_notes" (
    "id" text NOT NULL,
    "thread_id" text NOT NULL,
    "task_segment" bigint NOT NULL DEFAULT 1,
    "note_version" bigint NOT NULL DEFAULT 1,
    "covered_until_message_seq" bigint NOT NULL DEFAULT 0,
    "source_run_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "goal" text NOT NULL DEFAULT '',
    "explicit_constraints_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "searched_scope_and_material_refs_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "findings_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "open_questions_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "next_actions_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "dependencies_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "scope_version" bigint NOT NULL,
    "memory_generation" bigint NOT NULL DEFAULT 0,
    "status" text NOT NULL DEFAULT 'active',
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "checkpoint_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("thread_id","task_segment")
);

CREATE INDEX "idx_assistant_task_notes_thread" ON shiliu."assistant_task_notes" ("workspace_id", "thread_id", "task_segment", "note_version");

CREATE TABLE shiliu."assistant_threads" (
    "id" text NOT NULL,
    "principal_id" text NOT NULL,
    "space_id" bigint NOT NULL,
    "title" text NOT NULL DEFAULT '',
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "context_state_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("workspace_id","id")
);

CREATE INDEX "idx_assistant_threads_space" ON shiliu."assistant_threads" ("workspace_id", "principal_id", "space_id", "updated_at" DESC);

CREATE TABLE shiliu."assistant_tool_calls" (
    "id" text NOT NULL,
    "run_id" text NOT NULL,
    "ordinal" bigint NOT NULL,
    "call_id" text NOT NULL,
    "name" text NOT NULL,
    "args_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "result_json" jsonb,
    "operation_key" text,
    "created_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("run_id","ordinal"),
    UNIQUE ("run_id","call_id")
);

CREATE TABLE shiliu."assistant_wiki_changes" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "page_id" text NOT NULL,
    "version" bigint NOT NULL,
    "operation" text NOT NULL,
    "before_json" jsonb,
    "after_json" jsonb NOT NULL,
    "summary" text NOT NULL DEFAULT '',
    "actor" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("page_id","version")
);

CREATE TABLE shiliu."assistant_wiki_dependencies" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "page_id" text NOT NULL,
    "block_id" text NOT NULL,
    "source_revision" text NOT NULL,
    "video_id" bigint NOT NULL,
    "dependency_kind" text NOT NULL DEFAULT 'source',
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("page_id","block_id","source_revision")
);

CREATE INDEX "idx_assistant_wiki_dependencies_page" ON shiliu."assistant_wiki_dependencies" ("workspace_id", "page_id", "block_id");

CREATE TABLE shiliu."assistant_wiki_materials" (
    "page_id" text NOT NULL,
    "video_id" bigint NOT NULL,
    "source_revision" text NOT NULL,
    "relation" text NOT NULL,
    "status" text NOT NULL DEFAULT 'integrated',
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("page_id","video_id"),
    CHECK (relation IN ('supports_block','associated'))
);

CREATE INDEX "idx_assistant_wiki_materials_video" ON shiliu."assistant_wiki_materials" ("workspace_id", "video_id", "page_id");

CREATE TABLE shiliu."assistant_wiki_operation_states" (
    "page_id" text NOT NULL,
    "version" bigint NOT NULL,
    "before_json" jsonb,
    "after_json" jsonb NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("page_id","version")
);

CREATE TABLE shiliu."assistant_wiki_pages" (
    "id" text NOT NULL,
    "principal_id" text NOT NULL,
    "space_id" bigint NOT NULL,
    "normalized_title" text NOT NULL,
    "title" text NOT NULL,
    "aliases_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "page_type" text NOT NULL,
    "summary" text NOT NULL DEFAULT '',
    "blocks_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "version" bigint NOT NULL DEFAULT 1,
    "status" text NOT NULL DEFAULT 'active',
    "scope_version" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("principal_id","space_id","normalized_title"),
    UNIQUE ("workspace_id","id"),
    UNIQUE ("workspace_id","space_id","id"),
    CHECK (page_type IN ('concept','method','comparison','topic'))
);

CREATE INDEX "idx_assistant_wiki_pages_space" ON shiliu."assistant_wiki_pages" ("workspace_id", "principal_id", "space_id", "updated_at" DESC);

CREATE TABLE shiliu."assistant_wiki_personal_dependencies" (
    "page_id" text NOT NULL,
    "block_id" text NOT NULL,
    "memory_id" text NOT NULL,
    "memory_version" bigint NOT NULL,
    "source_message_id" text,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("page_id","block_id")
);

CREATE TABLE shiliu."assistant_wiki_proposals" (
    "id" text NOT NULL,
    "principal_id" text NOT NULL,
    "space_id" bigint NOT NULL,
    "kind" text NOT NULL,
    "source_page_id" text,
    "target_page_id" text NOT NULL,
    "source_version" bigint,
    "target_version" bigint NOT NULL,
    "input_fingerprint" text NOT NULL,
    "payload_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("principal_id","space_id","kind","target_page_id","input_fingerprint"),
    CHECK (status IN ('pending','accepted','rejected','stale'))
);

CREATE TABLE shiliu."assistant_wiki_redirects" (
    "old_page_id" text NOT NULL,
    "target_page_id" text NOT NULL,
    "space_id" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("old_page_id")
);

CREATE TABLE shiliu."knowledge_draft_revisions" (
    "draft_revision_id" text NOT NULL,
    "draft_id" text NOT NULL,
    "draft_schema_version" text NOT NULL,
    "version" bigint NOT NULL,
    "parent_revision_id" text,
    "owner_scope" text NOT NULL,
    "origin_kind" text NOT NULL,
    "ask_run_id" text,
    "research_task_id" text,
    "source_answer_snapshot_json" jsonb NOT NULL,
    "source_answer_hash" text NOT NULL,
    "evidence_refs_json" jsonb NOT NULL,
    "scope_json" jsonb NOT NULL,
    "limitations_json" jsonb NOT NULL,
    "revalidation_state" text NOT NULL,
    "status" text NOT NULL,
    "dedupe_identity" text NOT NULL,
    "materialization_task_id" text,
    "candidate_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "promotion_output_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "event_kind" text NOT NULL,
    "command_id" text NOT NULL,
    "command_payload_hash" text NOT NULL,
    "reason_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "owner_user_id" text NOT NULL,
    PRIMARY KEY ("draft_revision_id"),
    UNIQUE ("draft_id","version"),
    UNIQUE ("draft_id","command_id"),
    UNIQUE ("workspace_id","draft_revision_id"),
    CHECK (draft_schema_version='v5.6-knowledge-draft-v1'),
    CHECK (version >= 1),
    CHECK (owner_scope='local_user_workspace'),
    CHECK (origin_kind IN ('fast','deep','research')),
    CHECK (revalidation_state IN ('not_checked','current','needs_revalidation','blocked')),
    CHECK (status IN ('saved','materializing','promotion_ready','needs_revalidation', 'confirmed','failed','cancelled')),
    CHECK (event_kind IN ('saved','materialization_started','materialization_ready', 'materialization_failed','revalidation_blocked', 'promotion_confirmed','operation_failed', 'cancelled')),
    CHECK ((origin_kind IN ('fast','deep') AND ask_run_id IS NOT NULL AND research_task_id IS NULL) OR (origin_kind='research' AND ask_run_id IS NULL AND research_task_id IS NOT NULL)),
    CHECK ((version=1 AND parent_revision_id IS NULL) OR (version>1 AND parent_revision_id IS NOT NULL)),
    CHECK (version > 1 OR status <> 'confirmed')
);

CREATE UNIQUE INDEX "idx_knowledge_draft_initial_dedupe" ON shiliu."knowledge_draft_revisions" ("workspace_id", "owner_scope", "dedupe_identity") WHERE version=1;

CREATE INDEX "idx_knowledge_draft_latest" ON shiliu."knowledge_draft_revisions" ("workspace_id", "owner_scope", "draft_id", "version" DESC);

CREATE TABLE shiliu."metadata_backfill_job_holds" (
    "job_id" text NOT NULL,
    "run_id" text NOT NULL,
    "video_id" bigint NOT NULL,
    "reason" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("job_id")
);

CREATE TABLE shiliu."metadata_backfill_operations" (
    "run_id" text NOT NULL,
    "video_id" bigint NOT NULL,
    "bvid" text NOT NULL,
    "part" bigint NOT NULL,
    "candidate_json" jsonb NOT NULL,
    "candidate_sha256" text NOT NULL,
    "state" text NOT NULL,
    "old_published_at" bigint,
    "new_published_at" bigint,
    "old_metadata_observed_at" timestamptz,
    "new_metadata_observed_at" timestamptz,
    "old_updated_at" timestamptz,
    "new_updated_at" timestamptz,
    "dirty_generation_before" bigint,
    "dirty_generation_after" bigint,
    "old_head_revision" text,
    "new_head_revision" text,
    "held_job_ids_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "maintenance_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "detail" text,
    "written_at" timestamptz,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("run_id","video_id")
);

CREATE INDEX "idx_metadata_backfill_ops_state" ON shiliu."metadata_backfill_operations" ("workspace_id", "run_id", "state", "video_id");

CREATE TABLE shiliu."metadata_backfill_runs" (
    "run_id" text NOT NULL,
    "account_id" text NOT NULL,
    "target_sha256" text NOT NULL,
    "state" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("run_id"),
    UNIQUE ("workspace_id","run_id")
);

CREATE TABLE shiliu."metadata_backfill_wiki_intents" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "run_id" text NOT NULL,
    "video_id" bigint NOT NULL,
    "page_id" text NOT NULL,
    "old_revision" text NOT NULL,
    "new_revision" text NOT NULL,
    "before_version" bigint NOT NULL,
    "after_version" bigint,
    "job_id" text NOT NULL,
    "state" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("job_id"),
    UNIQUE ("run_id","video_id","page_id","old_revision","new_revision")
);

CREATE INDEX "idx_metadata_backfill_wiki_page" ON shiliu."metadata_backfill_wiki_intents" ("workspace_id", "run_id", "page_id", "id", "state");

CREATE TABLE shiliu."research_artifact_fact_links" (
    "link_id" text NOT NULL,
    "task_id" text NOT NULL,
    "artifact_revision_id" text NOT NULL,
    "fact_revision_id" text NOT NULL,
    "ordinal" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("link_id"),
    UNIQUE ("artifact_revision_id","fact_revision_id"),
    CHECK (ordinal >= 0)
);

CREATE TABLE shiliu."research_artifact_routes" (
    "record_id" text NOT NULL,
    "route_id" text NOT NULL,
    "version" bigint NOT NULL,
    "parent_record_id" text,
    "task_id" text NOT NULL,
    "record_kind" text NOT NULL,
    "command_id" text NOT NULL,
    "payload_hash" text NOT NULL,
    "query_json" jsonb NOT NULL,
    "retrieval_json" jsonb NOT NULL,
    "gates_json" jsonb NOT NULL,
    "recommended_route" text NOT NULL,
    "final_route" text,
    "expected_authority_hash" text NOT NULL,
    "continuation_task_id" text,
    "outcome_artifact_revision_id" text,
    "contribution_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("record_id"),
    UNIQUE ("route_id","version"),
    UNIQUE ("task_id","command_id"),
    UNIQUE ("workspace_id","task_id","record_id"),
    CHECK (version >= 1),
    CHECK (record_kind IN ('assessment', 'proceed', 'outcome')),
    CHECK (recommended_route IN ('direct_reuse', 'incremental_refresh', 'research_seed')),
    CHECK (final_route IS NULL OR final_route IN ('direct_reuse', 'incremental_refresh', 'research_seed')),
    CHECK (status IN ('assessed', 'running', 'completed', 'needs_user', 'superseded'))
);

CREATE INDEX "idx_research_artifact_routes_task" ON shiliu."research_artifact_routes" ("workspace_id", "task_id", "created_at", "route_id", "version");

CREATE TABLE shiliu."research_attempts" (
    "attempt_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "ordinal" bigint NOT NULL,
    "cause" text NOT NULL,
    "parent_attempt_id" text,
    "source_checkpoint_id" text,
    "status" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "result_id" text,
    "started_at" timestamptz,
    "ended_at" timestamptz,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("attempt_id"),
    UNIQUE ("task_id","ordinal"),
    UNIQUE ("workspace_id","task_id","attempt_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id"),
    CHECK (ordinal >= 1),
    CHECK (cause IN ('initial', 'resume', 'retry', 'goal_revision', 'branch', 'replay')),
    CHECK (status IN ('pending', 'running', 'blocked', 'waiting_user', 'terminal')),
    CHECK (owner_epoch >= 1)
);

CREATE UNIQUE INDEX "idx_research_attempts_one_active" ON shiliu."research_attempts" ("workspace_id", "task_id") WHERE status != 'terminal';

CREATE INDEX "idx_research_attempts_task" ON shiliu."research_attempts" ("workspace_id", "task_id", "ordinal");

CREATE TABLE shiliu."research_audit_candidates" (
    "candidate_id" text NOT NULL,
    "candidate_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "artifact_id" text NOT NULL,
    "producer_kind" text NOT NULL,
    "proposal_json" jsonb NOT NULL,
    "proposal_hash" text NOT NULL,
    "provider_side_effect_id" text,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("candidate_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","candidate_id"),
    CHECK (producer_kind IN ('deterministic', 'provider')),
    CHECK (owner_epoch >= 1)
);

CREATE TABLE shiliu."research_checkpoints" (
    "checkpoint_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "parent_checkpoint_id" text,
    "sequence" bigint NOT NULL,
    "state_schema_version" text NOT NULL,
    "state_hash" text NOT NULL,
    "state_payload_json" jsonb NOT NULL,
    "is_complete" boolean NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("checkpoint_id"),
    UNIQUE ("attempt_id","sequence"),
    UNIQUE ("workspace_id","task_id","checkpoint_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id"),
    CHECK (sequence >= 1),
    CHECK (is_complete IN (false,true)),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_checkpoints_attempt" ON shiliu."research_checkpoints" ("workspace_id", "attempt_id", "sequence");

CREATE TABLE shiliu."research_command_receipts" (
    "receipt_id" text NOT NULL,
    "task_id" text NOT NULL,
    "command_id" text NOT NULL,
    "command_type" text NOT NULL,
    "payload_hash" text NOT NULL,
    "status" text NOT NULL,
    "outcome_reference" text,
    "response_json" jsonb,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("receipt_id"),
    UNIQUE ("task_id","command_id"),
    CHECK (status IN ('accepted', 'committed', 'rejected')),
    CHECK (owner_epoch >= 0)
);

CREATE TABLE shiliu."research_compact_improvement_states" (
    "improvement_state_id" text NOT NULL,
    "improvement_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "audit_id" text NOT NULL,
    "source_checkpoint_id" text NOT NULL,
    "artifact_id" text NOT NULL,
    "state_payload_json" jsonb NOT NULL,
    "state_hash" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("improvement_state_id"),
    UNIQUE ("workspace_id","task_id","goal_id","improvement_state_id"),
    CHECK (owner_epoch >= 1)
);

CREATE TABLE shiliu."research_constraint_audit_observations" (
    "audit_observation_id" text NOT NULL,
    "audit_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "artifact_id" text NOT NULL,
    "constraint_id" text NOT NULL,
    "evaluator_policy_version" text NOT NULL,
    "status" text NOT NULL,
    "recoverability" text NOT NULL,
    "evidence_use_ids_json" jsonb NOT NULL,
    "validation_observation_ids_json" jsonb NOT NULL,
    "reason_codes_json" jsonb NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "observed_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("audit_observation_id"),
    CHECK (status IN ('satisfied', 'unsatisfied', 'unknown', 'invalid')),
    CHECK (recoverability IN ( 'recoverable', 'irrecoverable', 'needs_user', 'not_applicable' )),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_constraint_observations_audit" ON shiliu."research_constraint_audit_observations" ("workspace_id", "audit_id", "constraint_id");

CREATE TABLE shiliu."research_constraint_specs" (
    "constraint_id" text NOT NULL,
    "constraint_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "goal_revision" bigint NOT NULL,
    "ordinal" bigint NOT NULL,
    "constraint_scope" text NOT NULL,
    "original_text" text NOT NULL,
    "normalized_text" text NOT NULL,
    "constraint_kind" text NOT NULL,
    "is_required" boolean NOT NULL,
    "evaluator_policy_json" jsonb NOT NULL,
    "evaluator_policy_version" text NOT NULL,
    "canonical_payload_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("constraint_id"),
    UNIQUE ("goal_id","ordinal"),
    UNIQUE ("workspace_id","task_id","goal_id","constraint_id"),
    CHECK (goal_revision >= 1),
    CHECK (ordinal >= 0),
    CHECK (constraint_scope IN ('objective', 'success_constraint')),
    CHECK (length(trim(original_text)) > 0),
    CHECK (length(trim(normalized_text)) > 0),
    CHECK (is_required IN (false,true))
);

CREATE INDEX "idx_research_constraint_specs_goal" ON shiliu."research_constraint_specs" ("workspace_id", "task_id", "goal_id", "ordinal");

CREATE TABLE shiliu."research_continuation_decisions" (
    "continuation_decision_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "parent_attempt_id" text NOT NULL,
    "child_attempt_id" text,
    "audit_id" text NOT NULL,
    "improvement_state_id" text NOT NULL,
    "decision" text NOT NULL,
    "targeted_objective" text,
    "target_fingerprint" text,
    "reason_codes_json" jsonb NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "insertion_seq" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    PRIMARY KEY ("continuation_decision_id"),
    UNIQUE ("workspace_id","insertion_seq"),
    UNIQUE ("workspace_id","task_id","goal_id","continuation_decision_id"),
    CHECK (decision IN ( 'accept', 'targeted_continue', 'stop_partial', 'stop_insufficient', 'blocked' )),
    CHECK (owner_epoch >= 1),
    CHECK ((decision = 'targeted_continue' AND child_attempt_id IS NOT NULL AND targeted_objective IS NOT NULL AND target_fingerprint IS NOT NULL) OR (decision != 'targeted_continue' AND child_attempt_id IS NULL))
);

CREATE INDEX "idx_research_continuation_decisions_task" ON shiliu."research_continuation_decisions" ("workspace_id", "task_id", "goal_id", "created_at");

CREATE TABLE shiliu."research_continuation_seeds" (
    "seed_id" text NOT NULL,
    "seed_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "parent_attempt_id" text NOT NULL,
    "child_attempt_id" text NOT NULL,
    "continuation_decision_id" text NOT NULL,
    "audit_id" text NOT NULL,
    "source_checkpoint_id" text NOT NULL,
    "source_artifact_id" text NOT NULL,
    "targeted_objective" text NOT NULL,
    "target_fingerprint" text NOT NULL,
    "carry_evidence_ids_json" jsonb NOT NULL,
    "seed_payload_hash" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "insertion_seq" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    PRIMARY KEY ("seed_id"),
    UNIQUE ("child_attempt_id"),
    UNIQUE ("continuation_decision_id"),
    UNIQUE ("workspace_id","insertion_seq"),
    CHECK (length(trim(targeted_objective)) > 0),
    CHECK (owner_epoch >= 1)
);

CREATE TABLE shiliu."research_control_dispositions" (
    "disposition_id" text NOT NULL,
    "control_request_id" text NOT NULL,
    "task_id" text NOT NULL,
    "status" text NOT NULL,
    "observed_control_generation" bigint NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "reason" text NOT NULL,
    "resulting_references_json" jsonb NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("disposition_id"),
    CHECK (status IN ('accepted', 'applied', 'rejected', 'superseded')),
    CHECK (observed_control_generation >= 1),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_control_dispositions_request" ON shiliu."research_control_dispositions" ("workspace_id", "control_request_id", "created_at");

CREATE TABLE shiliu."research_control_requests" (
    "control_request_id" text NOT NULL,
    "control_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "attempt_id" text,
    "command_id" text NOT NULL,
    "request_kind" text NOT NULL,
    "payload_hash" text NOT NULL,
    "payload_json" jsonb NOT NULL,
    "audit_actor_metadata_json" jsonb NOT NULL,
    "principal_id" text NOT NULL,
    "expected_state_version" bigint NOT NULL,
    "expected_checkpoint_id" text,
    "expected_control_generation" bigint NOT NULL,
    "admitted_control_generation" bigint NOT NULL,
    "admitted_owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("control_request_id"),
    UNIQUE ("task_id","command_id"),
    UNIQUE ("workspace_id","task_id","control_request_id"),
    CHECK (request_kind IN ('interrupt', 'resume', 'cancel')),
    CHECK (expected_state_version >= 0),
    CHECK (expected_control_generation >= 0),
    CHECK (admitted_control_generation >= 1),
    CHECK (admitted_owner_epoch >= 1)
);

CREATE INDEX "idx_research_control_requests_task" ON shiliu."research_control_requests" ("workspace_id", "task_id", "created_at");

CREATE TABLE shiliu."research_events" (
    "event_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text,
    "attempt_id" text,
    "checkpoint_id" text,
    "sequence" bigint NOT NULL,
    "event_type" text NOT NULL,
    "payload_json" jsonb NOT NULL,
    "command_id" text,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("event_id"),
    UNIQUE ("task_id","sequence"),
    UNIQUE ("workspace_id","task_id","event_id"),
    CHECK (sequence >= 1),
    CHECK (owner_epoch >= 0)
);

CREATE INDEX "idx_research_events_task" ON shiliu."research_events" ("workspace_id", "task_id", "sequence");

CREATE TABLE shiliu."research_evidence_identities" (
    "evidence_id" text NOT NULL,
    "citation_identity_version" text NOT NULL,
    "video_id" bigint NOT NULL,
    "source_artifact_id" text NOT NULL,
    "source_version" text NOT NULL,
    "timeline_run_id" text NOT NULL,
    "segment_ids_json" jsonb NOT NULL,
    "segment_ordinals_json" jsonb NOT NULL,
    "start_time" double precision NOT NULL,
    "end_time" double precision NOT NULL,
    "quote_hash" text NOT NULL,
    "quote_preview" text NOT NULL,
    "identity_payload_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("evidence_id"),
    UNIQUE ("workspace_id","evidence_id"),
    CHECK (start_time >= 0),
    CHECK (end_time >= start_time)
);

CREATE TABLE shiliu."research_evidence_provenance" (
    "provenance_id" text NOT NULL,
    "evidence_use_id" text NOT NULL,
    "action_id" text NOT NULL,
    "execution_id" text,
    "search_trace_id" text,
    "query_fingerprint" text NOT NULL,
    "rank" bigint,
    "retrieval_method" text NOT NULL,
    "index_identity_json" jsonb NOT NULL,
    "parent_chunk_ids_json" jsonb NOT NULL,
    "source_version_authority" text NOT NULL,
    "mapping_policy_versions_json" jsonb NOT NULL,
    "provenance_hash" text NOT NULL,
    "observed_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    PRIMARY KEY ("provenance_id"),
    UNIQUE ("evidence_use_id","provenance_hash")
);

CREATE INDEX "idx_research_evidence_provenance_use" ON shiliu."research_evidence_provenance" ("workspace_id", "evidence_use_id", "observed_at");

CREATE TABLE shiliu."research_evidence_uses" (
    "evidence_use_id" text NOT NULL,
    "evidence_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "first_action_id" text NOT NULL,
    "originating_checkpoint_id" text,
    "owner_epoch" bigint NOT NULL,
    "use_purpose" text NOT NULL,
    "use_schema_version" text NOT NULL,
    "use_payload_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("evidence_use_id"),
    UNIQUE ("task_id","attempt_id","evidence_id"),
    UNIQUE ("workspace_id","evidence_use_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","evidence_use_id"),
    UNIQUE ("workspace_id","task_id","evidence_use_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","evidence_id","evidence_use_id"),
    UNIQUE ("workspace_id","task_id","evidence_id","evidence_use_id"),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_evidence_uses_task" ON shiliu."research_evidence_uses" ("workspace_id", "task_id", "attempt_id", "created_at");

CREATE TABLE shiliu."research_evidence_validations" (
    "observation_id" text NOT NULL,
    "evidence_use_id" text NOT NULL,
    "evidence_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "checkpoint_id" text,
    "validation_policy_version" text NOT NULL,
    "authority_mode" text NOT NULL,
    "expected_source_version" text NOT NULL,
    "observed_source_version" text,
    "outcome" text NOT NULL,
    "reason_code" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "observed_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("observation_id"),
    UNIQUE ("workspace_id","task_id","observation_id"),
    UNIQUE ("workspace_id","task_id","evidence_id","evidence_use_id","observation_id"),
    CHECK (outcome IN ('current', 'stale', 'missing', 'invalid', 'error')),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_evidence_validations_use" ON shiliu."research_evidence_validations" ("workspace_id", "evidence_use_id", "observed_at");

CREATE TABLE shiliu."research_execution_metadata" (
    "task_id" text NOT NULL,
    "time_policy_version" text NOT NULL,
    "active_budget_ms" bigint NOT NULL,
    "consumed_active_ms" bigint NOT NULL DEFAULT 0,
    "segment_id" text,
    "segment_owner_id" text,
    "segment_owner_epoch" bigint,
    "segment_settled_ms" bigint NOT NULL DEFAULT 0,
    "reserved_tail_ms" bigint NOT NULL DEFAULT 0,
    "tick_sequence" bigint NOT NULL DEFAULT 0,
    "timing_status" text NOT NULL DEFAULT 'idle',
    "scheduling_intent" text NOT NULL DEFAULT 'none',
    "scheduling_status" text NOT NULL DEFAULT 'idle',
    "run_command_id" text,
    "resume_reason" text,
    "automatic_failure_count" bigint NOT NULL DEFAULT 0,
    "lifetime_automatic_failure_count" bigint NOT NULL DEFAULT 0,
    "manual_generation" bigint NOT NULL DEFAULT 0,
    "next_retry_at" timestamptz,
    "last_failure_code" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("task_id"),
    CHECK (active_budget_ms > 0),
    CHECK (consumed_active_ms >= 0),
    CHECK (segment_settled_ms >= 0),
    CHECK (reserved_tail_ms >= 0),
    CHECK (tick_sequence >= 0),
    CHECK (timing_status IN ('idle','active','uncertain','exhausted')),
    CHECK (scheduling_intent IN ('none','queued','manual')),
    CHECK (scheduling_status IN ('idle','queued','running','backoff','manual_required','blocked','complete')),
    CHECK (automatic_failure_count >= 0),
    CHECK (lifetime_automatic_failure_count >= 0),
    CHECK (manual_generation >= 0),
    CHECK ((segment_id IS NULL AND segment_owner_id IS NULL AND segment_owner_epoch IS NULL) OR (segment_id IS NOT NULL AND segment_owner_id IS NOT NULL AND segment_owner_epoch IS NOT NULL))
);

CREATE INDEX "idx_research_execution_due" ON shiliu."research_execution_metadata" ("workspace_id", "scheduling_status", "next_retry_at", "updated_at");

CREATE TABLE shiliu."research_fact_evidence_links" (
    "link_id" text NOT NULL,
    "task_id" text NOT NULL,
    "fact_revision_id" text NOT NULL,
    "evidence_id" text NOT NULL,
    "evidence_use_id" text NOT NULL,
    "validation_observation_id" text NOT NULL,
    "ordinal" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("link_id"),
    UNIQUE ("fact_revision_id","evidence_use_id"),
    CHECK (ordinal >= 0)
);

CREATE TABLE shiliu."research_fact_revisions" (
    "fact_revision_id" text NOT NULL,
    "fact_id" text NOT NULL,
    "task_id" text NOT NULL,
    "revision" bigint NOT NULL,
    "parent_revision_id" text,
    "supersedes_revision_id" text,
    "origin_candidate_id" text NOT NULL,
    "claim_text" text NOT NULL,
    "temporal_scope_json" jsonb NOT NULL,
    "viewpoint_scope_json" jsonb NOT NULL,
    "verification_status" text NOT NULL,
    "content_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("fact_revision_id"),
    UNIQUE ("fact_id","revision"),
    UNIQUE ("workspace_id","task_id","fact_revision_id"),
    UNIQUE ("workspace_id","task_id","fact_id","fact_revision_id"),
    CHECK (revision >= 1),
    CHECK (length(trim(claim_text)) > 0),
    CHECK (verification_status='accepted_current')
);

CREATE INDEX "idx_research_fact_revisions_task" ON shiliu."research_fact_revisions" ("workspace_id", "task_id", "created_at");

CREATE TABLE shiliu."research_goals" (
    "goal_id" text NOT NULL,
    "task_id" text NOT NULL,
    "revision" bigint NOT NULL,
    "parent_goal_id" text,
    "objective" text NOT NULL,
    "success_constraints_json" jsonb NOT NULL,
    "evidence_policy_json" jsonb NOT NULL,
    "created_by_event_id" text,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("goal_id"),
    UNIQUE ("task_id","revision"),
    UNIQUE ("workspace_id","task_id","goal_id"),
    CHECK (revision >= 1),
    CHECK (length(trim(objective)) > 0)
);

CREATE INDEX "idx_research_goals_task" ON shiliu."research_goals" ("workspace_id", "task_id", "revision");

CREATE TABLE shiliu."research_grounded_facts" (
    "fact_id" text NOT NULL,
    "workspace_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "origin_candidate_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("fact_id"),
    UNIQUE ("origin_candidate_id"),
    UNIQUE ("workspace_id","task_id","fact_id")
);

CREATE TABLE shiliu."research_human_constraint_observations" (
    "observation_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "constraint_id" text NOT NULL,
    "decision_id" text NOT NULL,
    "selected_option" text NOT NULL,
    "evaluator_policy_version" text NOT NULL,
    "control_generation" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("observation_id"),
    UNIQUE ("decision_id"),
    CHECK (control_generation >= 1)
);

CREATE TABLE shiliu."research_human_decisions" (
    "decision_id" text NOT NULL,
    "input_request_id" text NOT NULL,
    "task_id" text NOT NULL,
    "command_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "decision_kind" text NOT NULL,
    "response_hash" text NOT NULL,
    "response_json" jsonb NOT NULL,
    "applied_action" text NOT NULL,
    "result_references_json" jsonb NOT NULL,
    "control_generation" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("decision_id"),
    UNIQUE ("input_request_id"),
    UNIQUE ("task_id","command_id"),
    UNIQUE ("workspace_id","task_id","decision_id"),
    CHECK (decision_kind IN ('clarify_goal', 'select_constraint_option')),
    CHECK (control_generation >= 1)
);

CREATE TABLE shiliu."research_inner_actions" (
    "action_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "originating_checkpoint_id" text,
    "action_kind" text NOT NULL,
    "action_schema_version" text NOT NULL,
    "action_key" text NOT NULL,
    "request_hash" text NOT NULL,
    "request_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "retrieval_execution_id" text,
    "retrieval_trace_id" text,
    "side_effect_id" text,
    "observation_json" jsonb NOT NULL,
    "error_code" text,
    "error_detail" text,
    "created_at" timestamptz NOT NULL,
    "started_at" timestamptz,
    "completed_at" timestamptz,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("action_id"),
    UNIQUE ("attempt_id","action_key"),
    UNIQUE ("workspace_id","action_id"),
    UNIQUE ("workspace_id","task_id","action_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","action_id"),
    CHECK (action_kind IN ( 'plan', 'navigation', 'transcript_search', 'transcript_window', 'provisional_synthesis' )),
    CHECK (status IN ( 'planned', 'reserved', 'running', 'succeeded', 'failed', 'unknown', 'rejected' )),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_inner_actions_task" ON shiliu."research_inner_actions" ("workspace_id", "task_id", "attempt_id", "created_at");

CREATE TABLE shiliu."research_input_dispositions" (
    "disposition_id" text NOT NULL,
    "input_request_id" text NOT NULL,
    "task_id" text NOT NULL,
    "status" text NOT NULL,
    "control_generation" bigint NOT NULL,
    "reason" text NOT NULL,
    "resulting_reference" text,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("disposition_id"),
    CHECK (status IN ('open', 'resolved', 'cancelled', 'superseded')),
    CHECK (control_generation >= 0)
);

CREATE INDEX "idx_research_input_dispositions_request" ON shiliu."research_input_dispositions" ("workspace_id", "input_request_id", "created_at");

CREATE TABLE shiliu."research_input_requests" (
    "input_request_id" text NOT NULL,
    "input_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "source_checkpoint_id" text NOT NULL,
    "command_id" text NOT NULL,
    "request_kind" text NOT NULL,
    "prompt" text NOT NULL,
    "choices_json" jsonb NOT NULL,
    "response_schema_json" jsonb NOT NULL,
    "constraint_id" text,
    "payload_hash" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "expires_at" timestamptz,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("input_request_id"),
    UNIQUE ("task_id","command_id"),
    UNIQUE ("workspace_id","task_id","input_request_id"),
    CHECK (request_kind IN ('clarification', 'constraint_choice')),
    CHECK (length(prompt) BETWEEN 1 AND 2000),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_input_requests_task" ON shiliu."research_input_requests" ("workspace_id", "task_id", "attempt_id", "created_at");

CREATE TABLE shiliu."research_knowledge_artifact_revisions" (
    "artifact_revision_id" text NOT NULL,
    "artifact_id" text NOT NULL,
    "task_id" text NOT NULL,
    "revision" bigint NOT NULL,
    "parent_revision_id" text,
    "supersedes_revision_id" text,
    "topic" text NOT NULL,
    "body_json" jsonb NOT NULL,
    "limitations_json" jsonb NOT NULL,
    "unresolved_json" jsonb NOT NULL,
    "build_policy_version" text NOT NULL,
    "source_result_ids_json" jsonb NOT NULL,
    "source_boundary_hashes_json" jsonb NOT NULL,
    "corpus_snapshot_json" jsonb NOT NULL,
    "input_hash" text NOT NULL,
    "content_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("artifact_revision_id"),
    UNIQUE ("artifact_id","revision"),
    UNIQUE ("task_id","input_hash"),
    UNIQUE ("workspace_id","task_id","artifact_revision_id"),
    CHECK (revision >= 1),
    CHECK (length(trim(topic)) > 0)
);

CREATE INDEX "idx_research_artifact_revisions_task" ON shiliu."research_knowledge_artifact_revisions" ("workspace_id", "task_id", "created_at");

CREATE TABLE shiliu."research_knowledge_artifacts" (
    "artifact_id" text NOT NULL,
    "workspace_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("artifact_id"),
    UNIQUE ("workspace_id","task_id","artifact_id")
);

CREATE TABLE shiliu."research_knowledge_build_runs" (
    "build_run_id" text NOT NULL,
    "workspace_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "build_kind" text NOT NULL,
    "command_id" text NOT NULL,
    "input_hash" text NOT NULL,
    "input_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "attempt_count" bigint NOT NULL,
    "output_reference" text,
    "error_code" text,
    "error_detail" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("build_run_id"),
    UNIQUE ("task_id","build_kind","input_hash"),
    CHECK (build_kind IN ('artifact', 'topic_page')),
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    CHECK (attempt_count >= 1)
);

CREATE INDEX "idx_research_knowledge_build_runs_task" ON shiliu."research_knowledge_build_runs" ("workspace_id", "task_id", "build_kind", "created_at");

CREATE TABLE shiliu."research_knowledge_candidates" (
    "candidate_id" text NOT NULL,
    "workspace_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "checkpoint_id" text,
    "result_id" text,
    "provisional_artifact_id" text NOT NULL,
    "source_event_id" text NOT NULL,
    "source_delta_snapshot_id" text NOT NULL,
    "candidate_kind" text NOT NULL,
    "source_boundary_hash" text NOT NULL,
    "source_delta_hash" text NOT NULL,
    "source_item_hash" text NOT NULL,
    "source_item_index" bigint NOT NULL,
    "parent_candidate_id" text,
    "claim_text" text NOT NULL,
    "citation_ids_json" jsonb NOT NULL,
    "evidence_use_ids_json" jsonb NOT NULL,
    "source_payload_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "state_version" bigint NOT NULL DEFAULT 0,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("candidate_id"),
    UNIQUE ("source_event_id","source_item_hash"),
    UNIQUE ("workspace_id","task_id","candidate_id"),
    CHECK (candidate_kind='KnowledgeDelta'),
    CHECK (source_item_index >= 0),
    CHECK (length(trim(claim_text)) > 0),
    CHECK (status IN ( 'pending_review', 'needs_revalidation', 'accepted', 'rejected', 'superseded' )),
    CHECK (state_version >= 0)
);

CREATE INDEX "idx_research_knowledge_candidates_task" ON shiliu."research_knowledge_candidates" ("workspace_id", "task_id", "status", "created_at");

CREATE TABLE shiliu."research_knowledge_conflict_observations" (
    "conflict_observation_id" text NOT NULL,
    "task_id" text NOT NULL,
    "left_fact_revision_id" text NOT NULL,
    "right_fact_revision_id" text NOT NULL,
    "scope_overlap" boolean NOT NULL,
    "resolution" text NOT NULL,
    "update_candidate_id" text NOT NULL,
    "reason" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("conflict_observation_id"),
    CHECK (scope_overlap IN (false,true)),
    CHECK (resolution IN ('confirmed_conflict', 'different_scope', 'coexists'))
);

CREATE TABLE shiliu."research_knowledge_exports" (
    "export_id" text NOT NULL,
    "task_id" text NOT NULL,
    "page_revision_id" text NOT NULL,
    "export_format" text NOT NULL,
    "content_hash" text NOT NULL,
    "relative_path" text NOT NULL,
    "operation_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("export_id"),
    UNIQUE ("page_revision_id","export_format","content_hash"),
    CHECK (export_format IN ('markdown', 'json'))
);

CREATE TABLE shiliu."research_knowledge_fact_states" (
    "fact_id" text NOT NULL,
    "task_id" text NOT NULL,
    "current_revision_id" text NOT NULL,
    "lifecycle_status" text NOT NULL,
    "currentness_status" text NOT NULL,
    "superseded_by_revision_id" text,
    "latest_observation_set_id" text,
    "state_version" bigint NOT NULL DEFAULT 0,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("fact_id"),
    CHECK (lifecycle_status IN ('current', 'retired', 'superseded')),
    CHECK (currentness_status IN ('current', 'stale', 'potential_conflict', 'conflicted')),
    CHECK (state_version >= 0)
);

CREATE TABLE shiliu."research_knowledge_lifecycle_decisions" (
    "decision_id" text NOT NULL,
    "task_id" text NOT NULL,
    "fact_id" text NOT NULL,
    "update_candidate_id" text NOT NULL,
    "decision_kind" text NOT NULL,
    "result_kind" text NOT NULL,
    "source_revision_id" text NOT NULL,
    "result_revision_id" text,
    "related_fact_revision_id" text,
    "reason" text NOT NULL,
    "expected_candidate_version" bigint NOT NULL,
    "expected_fact_state_version" bigint NOT NULL,
    "command_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("decision_id"),
    UNIQUE ("task_id","command_id"),
    CHECK (decision_kind IN ('accept', 'reject', 'edit')),
    CHECK (result_kind IN ('correct', 'retire', 'supersede', 'confirm_conflict', 'reject', 'edit')),
    CHECK (expected_candidate_version >= 0),
    CHECK (expected_fact_state_version >= 0)
);

CREATE TABLE shiliu."research_knowledge_revalidation_observations" (
    "observation_id" text NOT NULL,
    "observation_set_id" text NOT NULL,
    "task_id" text NOT NULL,
    "fact_revision_id" text NOT NULL,
    "evidence_id" text NOT NULL,
    "evidence_use_id" text NOT NULL,
    "validation_observation_id" text NOT NULL,
    "trigger_kind" text NOT NULL,
    "expected_source_version" text NOT NULL,
    "observed_source_version" text,
    "outcome" text NOT NULL,
    "reason_code" text NOT NULL,
    "policy_version" text NOT NULL,
    "input_hash" text NOT NULL,
    "observed_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("observation_id"),
    UNIQUE ("observation_set_id","evidence_use_id"),
    CHECK (trigger_kind IN ('explicit', 'source_change', 'update_operation', 'recovery')),
    CHECK (outcome IN ('current', 'stale', 'missing', 'invalid', 'error'))
);

CREATE INDEX "idx_research_knowledge_observations_fact" ON shiliu."research_knowledge_revalidation_observations" ("workspace_id", "fact_revision_id", "observed_at");

CREATE TABLE shiliu."research_knowledge_review_decisions" (
    "decision_id" text NOT NULL,
    "task_id" text NOT NULL,
    "candidate_id" text NOT NULL,
    "decision_kind" text NOT NULL,
    "reason" text NOT NULL,
    "edited_candidate_id" text,
    "fact_revision_id" text,
    "expected_candidate_version" bigint NOT NULL,
    "command_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("decision_id"),
    UNIQUE ("task_id","command_id"),
    CHECK (decision_kind IN ('accept', 'reject', 'edit')),
    CHECK (expected_candidate_version >= 0)
);

CREATE TABLE shiliu."research_knowledge_update_candidates" (
    "update_candidate_id" text NOT NULL,
    "task_id" text NOT NULL,
    "fact_id" text NOT NULL,
    "source_fact_revision_id" text NOT NULL,
    "related_fact_revision_id" text,
    "source_observation_set_id" text,
    "candidate_kind" text NOT NULL,
    "proposed_claim" text,
    "temporal_scope_json" jsonb NOT NULL,
    "viewpoint_scope_json" jsonb NOT NULL,
    "evidence_use_ids_json" jsonb NOT NULL,
    "affected_artifact_ids_json" jsonb NOT NULL,
    "affected_page_ids_json" jsonb NOT NULL,
    "validator_status" text NOT NULL,
    "status" text NOT NULL,
    "parent_candidate_id" text,
    "state_version" bigint NOT NULL DEFAULT 0,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("update_candidate_id"),
    UNIQUE ("workspace_id","task_id","update_candidate_id"),
    CHECK (candidate_kind IN ('source_rebind', 'new_evidence', 'user_correction', 'potential_conflict', 'retire', 'supersede')),
    CHECK (validator_status IN ('eligible', 'needs_revalidation')),
    CHECK (status IN ('pending_review', 'needs_revalidation', 'accepted', 'rejected', 'superseded')),
    CHECK (state_version >= 0)
);

CREATE INDEX "idx_research_knowledge_update_candidates_task" ON shiliu."research_knowledge_update_candidates" ("workspace_id", "task_id", "status", "created_at");

CREATE TABLE shiliu."research_knowledge_update_operations" (
    "operation_id" text NOT NULL,
    "task_id" text NOT NULL,
    "operation_kind" text NOT NULL,
    "target_reference" text NOT NULL,
    "dedup_key" text NOT NULL,
    "command_id" text NOT NULL,
    "input_hash" text NOT NULL,
    "input_json" jsonb NOT NULL,
    "expected_heads_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "attempt_count" bigint NOT NULL DEFAULT 0,
    "max_attempts" bigint NOT NULL,
    "error_class" text,
    "error_code" text,
    "error_detail" text,
    "next_attempt_at" timestamptz,
    "claimant_id" text,
    "lease_until" timestamptz,
    "claim_generation" bigint NOT NULL DEFAULT 0,
    "output_reference" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "finished_at" timestamptz,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("operation_id"),
    UNIQUE ("task_id","operation_kind","dedup_key"),
    UNIQUE ("workspace_id","task_id","operation_id"),
    CHECK (operation_kind IN ('refresh_knowledge', 'export_page')),
    CHECK (status IN ('pending', 'running', 'retry_wait', 'succeeded', 'needs_user', 'dead_letter', 'superseded', 'cancelled')),
    CHECK (attempt_count >= 0),
    CHECK (max_attempts BETWEEN 1 AND 10),
    CHECK (claim_generation >= 0)
);

CREATE INDEX "idx_research_knowledge_update_operations_recovery" ON shiliu."research_knowledge_update_operations" ("workspace_id", "task_id", "status", "next_attempt_at", "lease_until");

CREATE TABLE shiliu."research_outer_audits" (
    "audit_id" text NOT NULL,
    "audit_schema_version" text NOT NULL,
    "audit_policy_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "source_checkpoint_id" text NOT NULL,
    "artifact_id" text NOT NULL,
    "constraint_snapshot_hash" text NOT NULL,
    "observation_ids_json" jsonb NOT NULL,
    "validation_observation_ids_json" jsonb NOT NULL,
    "artifact_fingerprint" text NOT NULL,
    "evidence_fingerprint" text NOT NULL,
    "progress_fingerprint" text NOT NULL,
    "outcome" text NOT NULL,
    "blocker" text,
    "reason_codes_json" jsonb NOT NULL,
    "budget_before_json" jsonb NOT NULL,
    "budget_after_json" jsonb NOT NULL,
    "candidate_id" text,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "insertion_seq" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    PRIMARY KEY ("audit_id"),
    UNIQUE ("workspace_id","insertion_seq"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","audit_id"),
    UNIQUE ("workspace_id","task_id","goal_id","audit_id"),
    CHECK (outcome IN ( 'accept', 'targeted_continue', 'stop_partial', 'stop_insufficient', 'blocked', 'failed' )),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_outer_audits_task" ON shiliu."research_outer_audits" ("workspace_id", "task_id", "goal_id", "created_at");

CREATE TABLE shiliu."research_outer_result_links" (
    "result_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "audit_id" text NOT NULL,
    "artifact_id" text NOT NULL,
    "constraint_fingerprint" text NOT NULL,
    "validation_observation_ids_json" jsonb NOT NULL,
    "generation_policy_version" text NOT NULL,
    "audit_policy_version" text NOT NULL,
    "evaluator_policy_versions_json" jsonb NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("result_id")
);

CREATE TABLE shiliu."research_provisional_artifacts" (
    "artifact_id" text NOT NULL,
    "artifact_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "checkpoint_id" text NOT NULL,
    "objective" text NOT NULL,
    "answer_status" text NOT NULL,
    "answer_blocks_json" jsonb NOT NULL,
    "limitations_json" jsonb NOT NULL,
    "evidence_set_fingerprint" text NOT NULL,
    "evidence_use_ids_json" jsonb NOT NULL,
    "evidence_ids_json" jsonb NOT NULL,
    "validation_observation_ids_json" jsonb NOT NULL,
    "generation_policy_version" text NOT NULL,
    "validator_policy_version" text NOT NULL,
    "provider_side_effect_id" text,
    "artifact_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("artifact_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","artifact_id"),
    UNIQUE ("workspace_id","task_id","artifact_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id","artifact_id"),
    CHECK (answer_status IN ('valid_success', 'valid_partial', 'valid_insufficient'))
);

CREATE INDEX "idx_research_provisional_artifacts_task" ON shiliu."research_provisional_artifacts" ("workspace_id", "task_id", "attempt_id", "created_at");

CREATE TABLE shiliu."research_results" (
    "result_id" text NOT NULL,
    "task_id" text NOT NULL,
    "goal_id" text NOT NULL,
    "attempt_id" text,
    "checkpoint_id" text,
    "answer_status" text NOT NULL,
    "termination_reason" text NOT NULL,
    "failure_class" text NOT NULL,
    "reason_detail" text NOT NULL,
    "is_task_terminal" boolean NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("result_id"),
    UNIQUE ("workspace_id","task_id","goal_id","attempt_id","result_id"),
    UNIQUE ("workspace_id","task_id","result_id"),
    CHECK (answer_status IN ( 'valid_success', 'valid_partial', 'valid_insufficient', 'not_produced' )),
    CHECK (termination_reason IN ( 'answer_ready', 'budget_exhausted', 'no_new_evidence', 'repeated_action', 'evidence_unavailable', 'needs_user_input', 'cancelled', 'goal_revised', 'external_side_effect_unknown', 'provider_error', 'implementation_error', 'targeted_continuation', 'constraint_unsatisfied' )),
    CHECK (failure_class IN ( 'none', 'implementation_failure', 'provider_failure', 'product_quality_failure', 'infrastructure_invalid_run', 'evaluation_invalid_run' )),
    CHECK (is_task_terminal IN (false,true)),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_results_task" ON shiliu."research_results" ("workspace_id", "task_id", "created_at");

CREATE TABLE shiliu."research_side_effect_resolutions" (
    "resolution_id" text NOT NULL,
    "side_effect_id" text NOT NULL,
    "task_id" text NOT NULL,
    "command_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "resolution" text NOT NULL,
    "reason" text NOT NULL,
    "receipt_hash" text,
    "result_reference" text,
    "control_generation" bigint NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("resolution_id"),
    UNIQUE ("side_effect_id"),
    UNIQUE ("task_id","command_id"),
    CHECK (resolution IN ('confirmed_succeeded', 'confirmed_failed')),
    CHECK (control_generation >= 1),
    CHECK (owner_epoch >= 1),
    CHECK (resolution != 'confirmed_succeeded' OR (receipt_hash IS NOT NULL AND result_reference IS NOT NULL))
);

CREATE TABLE shiliu."research_side_effects" (
    "side_effect_id" text NOT NULL,
    "task_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "command_id" text NOT NULL,
    "idempotency_key" text NOT NULL,
    "effect_kind" text NOT NULL,
    "request_hash" text NOT NULL,
    "request_json" jsonb NOT NULL,
    "status" text NOT NULL,
    "owner_epoch" bigint NOT NULL,
    "provider_operation_id" text,
    "receipt_hash" text,
    "result_reference" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("side_effect_id"),
    UNIQUE ("task_id","effect_kind","idempotency_key"),
    UNIQUE ("workspace_id","task_id","side_effect_id"),
    UNIQUE ("workspace_id","task_id","attempt_id","side_effect_id"),
    CHECK (status IN ('reserved', 'in_flight', 'succeeded', 'failed', 'unknown')),
    CHECK (owner_epoch >= 1)
);

CREATE INDEX "idx_research_side_effects_recovery" ON shiliu."research_side_effects" ("workspace_id", "task_id", "status", "owner_epoch");

CREATE TABLE shiliu."research_task_derivations" (
    "derivation_id" text NOT NULL,
    "derivation_schema_version" text NOT NULL,
    "source_task_id" text NOT NULL,
    "source_goal_id" text NOT NULL,
    "source_attempt_id" text NOT NULL,
    "source_checkpoint_id" text NOT NULL,
    "child_task_id" text NOT NULL,
    "child_goal_id" text NOT NULL,
    "child_attempt_id" text NOT NULL,
    "command_id" text NOT NULL,
    "derivation_kind" text NOT NULL,
    "source_state_hash" text NOT NULL,
    "source_manifest_json" jsonb NOT NULL,
    "goal_delta_json" jsonb NOT NULL,
    "payload_hash" text NOT NULL,
    "principal_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("derivation_id"),
    UNIQUE ("child_task_id"),
    UNIQUE ("child_attempt_id"),
    UNIQUE ("source_task_id","command_id"),
    CHECK (derivation_kind IN ('branch', 'replay'))
);

CREATE INDEX "idx_research_derivations_source" ON shiliu."research_task_derivations" ("workspace_id", "source_task_id", "created_at");

CREATE TABLE shiliu."research_tasks" (
    "task_id" text NOT NULL,
    "parent_task_id" text,
    "status" text NOT NULL,
    "active_goal_id" text,
    "state_version" bigint NOT NULL DEFAULT 0,
    "owner_id" text,
    "owner_epoch" bigint NOT NULL DEFAULT 0,
    "control_generation" bigint NOT NULL DEFAULT 0,
    "lease_until" timestamptz,
    "terminal_result_id" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    "owner_user_id" text NOT NULL,
    PRIMARY KEY ("task_id"),
    UNIQUE ("workspace_id","task_id"),
    CHECK (status IN ('ready', 'running', 'blocked', 'waiting_user', 'terminal')),
    CHECK (state_version >= 0),
    CHECK (owner_epoch >= 0),
    CHECK (control_generation >= 0),
    CHECK ((status = 'terminal' AND terminal_result_id IS NOT NULL) OR (status != 'terminal' AND terminal_result_id IS NULL))
);

CREATE INDEX "idx_research_tasks_parent" ON shiliu."research_tasks" ("workspace_id", "parent_task_id");

CREATE INDEX "idx_research_tasks_status" ON shiliu."research_tasks" ("workspace_id", "status", "updated_at");

CREATE TABLE shiliu."research_topic_page_fact_links" (
    "link_id" text NOT NULL,
    "task_id" text NOT NULL,
    "page_revision_id" text NOT NULL,
    "fact_revision_id" text NOT NULL,
    "ordinal" bigint NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("link_id"),
    UNIQUE ("page_revision_id","fact_revision_id"),
    CHECK (ordinal >= 0)
);

CREATE TABLE shiliu."research_topic_page_review_decisions" (
    "decision_id" text NOT NULL,
    "task_id" text NOT NULL,
    "page_id" text NOT NULL,
    "page_revision_id" text NOT NULL,
    "decision_kind" text NOT NULL,
    "reason" text NOT NULL,
    "expected_version" bigint NOT NULL,
    "command_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("decision_id"),
    UNIQUE ("task_id","command_id"),
    CHECK (decision_kind IN ('publish', 'return')),
    CHECK (expected_version >= 1)
);

CREATE TABLE shiliu."research_topic_page_revision_decisions" (
    "decision_id" text NOT NULL,
    "task_id" text NOT NULL,
    "page_id" text NOT NULL,
    "source_revision_id" text NOT NULL,
    "result_revision_id" text NOT NULL,
    "decision_kind" text NOT NULL,
    "reason" text NOT NULL,
    "command_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("decision_id"),
    UNIQUE ("task_id","command_id"),
    CHECK (decision_kind IN ('edit', 'revert', 'refresh'))
);

CREATE TABLE shiliu."research_topic_page_revisions" (
    "page_revision_id" text NOT NULL,
    "page_id" text NOT NULL,
    "task_id" text NOT NULL,
    "version" bigint NOT NULL,
    "parent_revision_id" text,
    "supersedes_revision_id" text,
    "revert_of_revision_id" text,
    "revision_kind" text NOT NULL,
    "artifact_revision_id" text NOT NULL,
    "title" text NOT NULL,
    "body_json" jsonb NOT NULL,
    "build_policy_version" text NOT NULL,
    "input_hash" text NOT NULL,
    "content_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("page_revision_id"),
    UNIQUE ("page_id","version"),
    UNIQUE ("task_id","input_hash"),
    UNIQUE ("workspace_id","task_id","page_revision_id"),
    UNIQUE ("workspace_id","task_id","page_id","page_revision_id"),
    CHECK (version >= 1),
    CHECK (revision_kind IN ('initial', 'refresh', 'edit', 'revert')),
    CHECK (length(trim(title)) > 0)
);

CREATE TABLE shiliu."research_topic_pages" (
    "page_id" text NOT NULL,
    "workspace_schema_version" text NOT NULL,
    "task_id" text NOT NULL,
    "slug" text NOT NULL,
    "current_version" bigint NOT NULL,
    "published_version" bigint,
    "review_status" text NOT NULL,
    "state_version" bigint NOT NULL DEFAULT 0,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("page_id"),
    UNIQUE ("slug"),
    UNIQUE ("workspace_id","task_id","page_id"),
    CHECK (current_version >= 1),
    CHECK (published_version IS NULL OR (published_version >= 1 AND published_version <= current_version)),
    CHECK (review_status IN ('draft', 'published', 'returned')),
    CHECK (state_version >= 0)
);

CREATE INDEX "idx_research_topic_pages_task" ON shiliu."research_topic_pages" ("workspace_id", "task_id", "created_at");

CREATE TABLE shiliu."research_traces" (
    "trace_id" text NOT NULL,
    "task_id" text NOT NULL,
    "attempt_id" text NOT NULL,
    "trace_schema_version" text NOT NULL,
    "started_at" timestamptz NOT NULL,
    "ended_at" timestamptz,
    "termination_reason" text,
    "retention_class" text NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("trace_id")
);

CREATE INDEX "idx_research_traces_task" ON shiliu."research_traces" ("workspace_id", "task_id", "started_at");

CREATE TABLE shiliu."research_workspace_records" (
    "record_revision_id" text NOT NULL,
    "record_id" text NOT NULL,
    "version" bigint NOT NULL,
    "parent_revision_id" text,
    "command_task_id" text NOT NULL,
    "record_kind" text NOT NULL,
    "authority_class" text NOT NULL,
    "status" text NOT NULL,
    "semantic_key" text NOT NULL,
    "payload_json" jsonb NOT NULL,
    "source_refs_json" jsonb NOT NULL,
    "source_boundary_hash" text NOT NULL,
    "confidence" double precision,
    "expires_at" timestamptz,
    "decision_action" text NOT NULL,
    "reason" text NOT NULL,
    "principal_id" text NOT NULL,
    "policy_version" text NOT NULL,
    "content_hash" text NOT NULL,
    "command_id" text NOT NULL,
    "command_payload_hash" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("record_revision_id"),
    UNIQUE ("record_id","version"),
    UNIQUE ("command_task_id","command_id"),
    UNIQUE ("workspace_id","record_revision_id"),
    CHECK (version >= 1),
    CHECK (record_kind IN ( 'explicit_memory', 'inferred_candidate', 'focus_state', 'progress_observation', 'corpus_observation', 'system_experience' )),
    CHECK (authority_class IN ( 'user_authored', 'user_confirmed', 'behavioral_candidate', 'evidence_backed_observation', 'corpus_soft_prior', 'experience_candidate' )),
    CHECK (status IN ( 'current', 'candidate', 'confirmed', 'rejected', 'expired', 'tombstoned', 'superseded', 'invalidated', 'observed', 'diagnosed', 'candidate_source' )),
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX "idx_research_workspace_records_projection" ON shiliu."research_workspace_records" ("workspace_id", "record_kind", "semantic_key", "record_id", "version");

ALTER TABLE shiliu."ask_events" ADD CONSTRAINT "fk_a76a3d72addef31efe5c" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."ask_events" ADD CONSTRAINT "fk_dc5f9d20a173b0f52f25" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."ask_runs" ("workspace_id","run_id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."ask_runs" ADD CONSTRAINT "fk_b92fada48cc509701404" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."ask_runs" ADD CONSTRAINT "fk_d2b7c7e9bfceabbb72dc" FOREIGN KEY ("workspace_id","owner_user_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."ask_runs" ADD CONSTRAINT "fk_cca034e2e4697de90a06" FOREIGN KEY ("workspace_id","parent_run_id") REFERENCES shiliu."ask_runs" ("workspace_id","run_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."ask_search_trace_links" ADD CONSTRAINT "fk_74083130a83a7ffa84f7" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."ask_search_trace_links" ADD CONSTRAINT "fk_6db68f7171d5488b3f4d" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."ask_runs" ("workspace_id","run_id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_jobs" ADD CONSTRAINT "fk_bf08ae8c166ecebee685" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_jobs" ADD CONSTRAINT "fk_3d44048fb43ee116c518" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_jobs" ADD CONSTRAINT "fk_355c3b68f5af1234788f" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_knowledge_plans" ADD CONSTRAINT "fk_c5df4699b348bd56376a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_knowledge_plans" ADD CONSTRAINT "fk_8f67e1779e11e1e5b21b" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_knowledge_plans" ADD CONSTRAINT "fk_abd4d8cee1d2138b2c45" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_knowledge_plans" ADD CONSTRAINT "fk_3c2316608ba2699e8645" FOREIGN KEY ("workspace_id","space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_knowledge_plans" ADD CONSTRAINT "fk_51b5cd7a08ec9e14562a" FOREIGN KEY ("workspace_id","source_message_id") REFERENCES shiliu."assistant_messages" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_maintenance_batches" ADD CONSTRAINT "fk_148e156c1a4da129247c" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_maintenance_batches" ADD CONSTRAINT "fk_7444dd8ed2b8c7419921" FOREIGN KEY ("workspace_id","space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memories" ADD CONSTRAINT "fk_d6bc3f28080d18dc0bee" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memories" ADD CONSTRAINT "fk_fdb40d9264668cdb349c" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memories" ADD CONSTRAINT "fk_ac06a034805bd2f43602" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memories" ADD CONSTRAINT "fk_6fdf7a82b011737aa1c7" FOREIGN KEY ("workspace_id","principal_id","scope_space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","principal_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memories" ADD CONSTRAINT "fk_f4fe0252e4e44d32dae8" FOREIGN KEY ("workspace_id","supersedes_id") REFERENCES shiliu."assistant_memories" ("workspace_id","id") ON DELETE SET NULL ("supersedes_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memory_changes" ADD CONSTRAINT "fk_36de1bbfcc0cde46fdbc" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memory_changes" ADD CONSTRAINT "fk_fb8fcb76017bf50a16dc" FOREIGN KEY ("workspace_id","memory_id") REFERENCES shiliu."assistant_memories" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memory_suppressions" ADD CONSTRAINT "fk_c9a181b3dbb62ef6ee57" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memory_suppressions" ADD CONSTRAINT "fk_17581ba0316b7dc33b92" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_memory_suppressions" ADD CONSTRAINT "fk_92ed2168235ce1215ad9" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_messages" ADD CONSTRAINT "fk_19d9d9249ce834704f81" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_messages" ADD CONSTRAINT "fk_f92133bb195ffa3d63bc" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."assistant_runs" ("workspace_id","id") ON DELETE SET NULL ("run_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_messages" ADD CONSTRAINT "fk_8a3dae8e51c2686b4100" FOREIGN KEY ("workspace_id","thread_id") REFERENCES shiliu."assistant_threads" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_messages" ADD CONSTRAINT "fk_104f437f7446d595c82b" FOREIGN KEY ("workspace_id","thread_id","run_id") REFERENCES shiliu."assistant_runs" ("workspace_id","thread_id","id") ON DELETE SET NULL ("run_id") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_model_budget_days" ADD CONSTRAINT "fk_15620ccbb59037790e6b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_model_budget_days" ADD CONSTRAINT "fk_da92ceb7cdb5aef0ee85" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_model_budget_days" ADD CONSTRAINT "fk_b6c5e426225286a80a32" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_mutation_receipts" ADD CONSTRAINT "fk_1ad5dbf5ad87c0133e4e" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_mutation_receipts" ADD CONSTRAINT "fk_da43ffa58343b4487270" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_mutation_receipts" ADD CONSTRAINT "fk_4b63defe5c02e768ea30" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_run_events" ADD CONSTRAINT "fk_1560f886ac521097c98b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_run_events" ADD CONSTRAINT "fk_a0ff240df12bae135a0b" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."assistant_runs" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_runs" ADD CONSTRAINT "fk_e7a19d557bdc4284b6fc" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_runs" ADD CONSTRAINT "fk_8f09f7306274377bc1a0" FOREIGN KEY ("workspace_id","thread_id") REFERENCES shiliu."assistant_threads" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_runtime_state" ADD CONSTRAINT "fk_43891a3d6636567f81c1" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_runtime_state" ADD CONSTRAINT "fk_f00e9f1dadddfc20c898" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_runtime_state" ADD CONSTRAINT "fk_3daf7316869696efb78a" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_scheduler_events" ADD CONSTRAINT "fk_0cf803ba71c98201afd8" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_scheduler_events" ADD CONSTRAINT "fk_2c50094185470a908792" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_scheduler_events" ADD CONSTRAINT "fk_1db11491858859141889" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_scheduler_events" ADD CONSTRAINT "fk_4fc44d4759a68bd0f312" FOREIGN KEY ("workspace_id","job_id") REFERENCES shiliu."assistant_jobs" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_card_batches" ADD CONSTRAINT "fk_2200742daee7010155b6" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_card_batches" ADD CONSTRAINT "fk_2db18bf3dab2794838aa" FOREIGN KEY ("workspace_id","revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","revision") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_cards" ADD CONSTRAINT "fk_21e68e875a6ea01ba53f" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_cards" ADD CONSTRAINT "fk_63626b01fb8d31c31ff9" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_cards" ADD CONSTRAINT "fk_fcd23537aac63e4e1679" FOREIGN KEY ("workspace_id","revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","revision") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_cards" ADD CONSTRAINT "fk_090d98dc99bb93fab719" FOREIGN KEY ("workspace_id","video_id","revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","video_id","revision") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_dirty" ADD CONSTRAINT "fk_037153035841587b7d12" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_dirty" ADD CONSTRAINT "fk_d92f53e71938ce430e45" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_heads" ADD CONSTRAINT "fk_d2eedf0560ca5b1e53c5" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_heads" ADD CONSTRAINT "fk_b5b73b6d7233119c884c" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_heads" ADD CONSTRAINT "fk_b611509cf27364bb5c0b" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_heads" ADD CONSTRAINT "fk_f874bdfe432bb3a480f8" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_heads" ADD CONSTRAINT "fk_85b1a14d4388a492195e" FOREIGN KEY ("workspace_id","current_revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","revision") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_heads" ADD CONSTRAINT "fk_884a33a17b24e26cfb90" FOREIGN KEY ("workspace_id","id","current_revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","head_id","revision") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_revisions" ADD CONSTRAINT "fk_aa165476fd6fc75107d1" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_revisions" ADD CONSTRAINT "fk_9894e9b8ba6fa0941a94" FOREIGN KEY ("workspace_id","head_id") REFERENCES shiliu."assistant_source_heads" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_source_revisions" ADD CONSTRAINT "fk_ffab22e0f346d085f981" FOREIGN KEY ("workspace_id","video_id","head_id") REFERENCES shiliu."assistant_source_heads" ("workspace_id","video_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_spaces" ADD CONSTRAINT "fk_bdefbfd636cd4200571c" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_spaces" ADD CONSTRAINT "fk_43c3a959e987ad3e9f17" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_spaces" ADD CONSTRAINT "fk_cca1b805c539694afc66" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_task_notes" ADD CONSTRAINT "fk_b12021c097d3790a9056" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_task_notes" ADD CONSTRAINT "fk_2e118523aba611fb891f" FOREIGN KEY ("workspace_id","thread_id") REFERENCES shiliu."assistant_threads" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_threads" ADD CONSTRAINT "fk_5e6dd60ed0c52341c68a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_threads" ADD CONSTRAINT "fk_2709213dff6ada2fe605" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_threads" ADD CONSTRAINT "fk_384433bc5a41c2cf7b53" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_threads" ADD CONSTRAINT "fk_e10adb3c4821a45a5644" FOREIGN KEY ("workspace_id","space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_tool_calls" ADD CONSTRAINT "fk_36013fe9e5cdb1a20235" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_tool_calls" ADD CONSTRAINT "fk_bddbfa29695ef7b0b89b" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."assistant_runs" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_changes" ADD CONSTRAINT "fk_9c40f940ad5714065a00" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_changes" ADD CONSTRAINT "fk_bf2d7f69287a1131e8ea" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_dependencies" ADD CONSTRAINT "fk_370afef92d2895923c6d" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_dependencies" ADD CONSTRAINT "fk_d058d022afc702338d4a" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_dependencies" ADD CONSTRAINT "fk_89b941986174ca664f9b" FOREIGN KEY ("workspace_id","source_revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","revision") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_dependencies" ADD CONSTRAINT "fk_563046131548fce4a761" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_dependencies" ADD CONSTRAINT "fk_9d5a994d89ca76bfe21f" FOREIGN KEY ("workspace_id","video_id","source_revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","video_id","revision") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_materials" ADD CONSTRAINT "fk_2a7e65c35e6d30420326" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_materials" ADD CONSTRAINT "fk_f77896f2ad7b9e8e9a5b" FOREIGN KEY ("workspace_id","source_revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","revision") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_materials" ADD CONSTRAINT "fk_46d0269bfe8596e33fb3" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_materials" ADD CONSTRAINT "fk_e2db915953ecbd5833c3" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_materials" ADD CONSTRAINT "fk_389f4bab07fc0ab2144c" FOREIGN KEY ("workspace_id","video_id","source_revision") REFERENCES shiliu."assistant_source_revisions" ("workspace_id","video_id","revision") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_operation_states" ADD CONSTRAINT "fk_200ebc18f7d8610fe84f" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_operation_states" ADD CONSTRAINT "fk_40e5714c83b723a34308" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_pages" ADD CONSTRAINT "fk_045d7601986c67696fc9" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_pages" ADD CONSTRAINT "fk_6660b598cfc0438da39c" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_pages" ADD CONSTRAINT "fk_ab41f04dc8f61bdb5558" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_pages" ADD CONSTRAINT "fk_3529f38c252ae9677630" FOREIGN KEY ("workspace_id","space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_personal_dependencies" ADD CONSTRAINT "fk_95789fe3905bd7ae4ce0" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_personal_dependencies" ADD CONSTRAINT "fk_213fed754713d0f85096" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_personal_dependencies" ADD CONSTRAINT "fk_77869dd98f251b2c0fe6" FOREIGN KEY ("workspace_id","memory_id") REFERENCES shiliu."assistant_memories" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_personal_dependencies" ADD CONSTRAINT "fk_92075a271bf75c500de2" FOREIGN KEY ("workspace_id","source_message_id") REFERENCES shiliu."assistant_messages" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_c3ebc01d85d4b3e92230" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_ed03c31672519554195d" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_c817c2c382fc18023bb3" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_e40f8495419e039f4c3c" FOREIGN KEY ("workspace_id","target_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_d363e7254183b2da82ed" FOREIGN KEY ("workspace_id","source_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_6aa85110433e4f709216" FOREIGN KEY ("workspace_id","space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_7fee00d527a0cae5749a" FOREIGN KEY ("workspace_id","space_id","source_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","space_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_proposals" ADD CONSTRAINT "fk_eadde5e381256310eec6" FOREIGN KEY ("workspace_id","space_id","target_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","space_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_redirects" ADD CONSTRAINT "fk_d5ff651386908906c891" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_redirects" ADD CONSTRAINT "fk_8d7b9f6fbacafabfe477" FOREIGN KEY ("workspace_id","space_id") REFERENCES shiliu."assistant_spaces" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_redirects" ADD CONSTRAINT "fk_59e84871d3b06b003d3e" FOREIGN KEY ("workspace_id","target_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_redirects" ADD CONSTRAINT "fk_0fbac83ed67de11655a6" FOREIGN KEY ("workspace_id","old_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_redirects" ADD CONSTRAINT "fk_d9f1200c1834b03fb0c2" FOREIGN KEY ("workspace_id","space_id","target_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","space_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_wiki_redirects" ADD CONSTRAINT "fk_abe792be964852e3a79e" FOREIGN KEY ("workspace_id","space_id","old_page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","space_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."knowledge_draft_revisions" ADD CONSTRAINT "fk_616e8ace2f9a77441f0a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."knowledge_draft_revisions" ADD CONSTRAINT "fk_06692c45dd53e3a44f8e" FOREIGN KEY ("workspace_id","owner_user_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."knowledge_draft_revisions" ADD CONSTRAINT "fk_036c4e85d1bb78eec6f9" FOREIGN KEY ("workspace_id","materialization_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."knowledge_draft_revisions" ADD CONSTRAINT "fk_601891bbad95f6891176" FOREIGN KEY ("workspace_id","research_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."knowledge_draft_revisions" ADD CONSTRAINT "fk_cbe9a3c5e9640c31fa4f" FOREIGN KEY ("workspace_id","ask_run_id") REFERENCES shiliu."ask_runs" ("workspace_id","run_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."knowledge_draft_revisions" ADD CONSTRAINT "fk_65161afcded405faf29b" FOREIGN KEY ("workspace_id","parent_revision_id") REFERENCES shiliu."knowledge_draft_revisions" ("workspace_id","draft_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_job_holds" ADD CONSTRAINT "fk_ad64f86f2589ad9dba25" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_job_holds" ADD CONSTRAINT "fk_8e07ced1d5ed24c48716" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."metadata_backfill_runs" ("workspace_id","run_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_job_holds" ADD CONSTRAINT "fk_c562068a038466cd8f43" FOREIGN KEY ("workspace_id","job_id") REFERENCES shiliu."assistant_jobs" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_operations" ADD CONSTRAINT "fk_08914dc438f017e0f288" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_operations" ADD CONSTRAINT "fk_4d95c61aa43b53cc8629" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."metadata_backfill_runs" ("workspace_id","run_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_operations" ADD CONSTRAINT "fk_67f071e1137b51c4f66e" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_runs" ADD CONSTRAINT "fk_ad22062a04d870e3ffdc" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_wiki_intents" ADD CONSTRAINT "fk_5c6b67617a00f884412c" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_wiki_intents" ADD CONSTRAINT "fk_78f62c3a567646cd11d8" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."metadata_backfill_runs" ("workspace_id","run_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_wiki_intents" ADD CONSTRAINT "fk_1bf43973e0fd3e88c165" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_wiki_intents" ADD CONSTRAINT "fk_7f2d66df4efaace046fd" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."metadata_backfill_wiki_intents" ADD CONSTRAINT "fk_38c2215b474df98ade01" FOREIGN KEY ("workspace_id","job_id") REFERENCES shiliu."assistant_jobs" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_fact_links" ADD CONSTRAINT "fk_478e3bef6e843a132c46" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_fact_links" ADD CONSTRAINT "fk_a2292f1b4d7d6040b70f" FOREIGN KEY ("workspace_id","task_id","fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_fact_links" ADD CONSTRAINT "fk_084a16ab59715bbe37ae" FOREIGN KEY ("workspace_id","task_id","artifact_revision_id") REFERENCES shiliu."research_knowledge_artifact_revisions" ("workspace_id","task_id","artifact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_fact_links" ADD CONSTRAINT "fk_b6f31459c6b39bf1dea2" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_routes" ADD CONSTRAINT "fk_f0f44211e7dea712c6e5" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_routes" ADD CONSTRAINT "fk_d0fa8aab6e84a7f6c53c" FOREIGN KEY ("workspace_id","task_id","outcome_artifact_revision_id") REFERENCES shiliu."research_knowledge_artifact_revisions" ("workspace_id","task_id","artifact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_routes" ADD CONSTRAINT "fk_e3013bcfa810dd84e515" FOREIGN KEY ("workspace_id","continuation_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_routes" ADD CONSTRAINT "fk_fe2fd5fe0db7816ef445" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_artifact_routes" ADD CONSTRAINT "fk_8d5054ac80686c273985" FOREIGN KEY ("workspace_id","task_id","parent_record_id") REFERENCES shiliu."research_artifact_routes" ("workspace_id","task_id","record_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_attempts" ADD CONSTRAINT "fk_1abaf40019571399f6b5" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_attempts" ADD CONSTRAINT "fk_4998609cf0eb1ccd4ee0" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","result_id") REFERENCES shiliu."research_results" ("workspace_id","task_id","goal_id","attempt_id","result_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_attempts" ADD CONSTRAINT "fk_bf894ba839d15e052d10" FOREIGN KEY ("workspace_id","task_id","source_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_attempts" ADD CONSTRAINT "fk_2f08791f6e3ded95311e" FOREIGN KEY ("workspace_id","task_id","parent_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_attempts" ADD CONSTRAINT "fk_fc4882aacf97f4d93a84" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_attempts" ADD CONSTRAINT "fk_0e2aed42ad3c2aa95415" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_audit_candidates" ADD CONSTRAINT "fk_ea1ee5417737aae8a558" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_audit_candidates" ADD CONSTRAINT "fk_f5b1158e3a72121172f1" FOREIGN KEY ("workspace_id","task_id","provider_side_effect_id") REFERENCES shiliu."research_side_effects" ("workspace_id","task_id","side_effect_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_audit_candidates" ADD CONSTRAINT "fk_de8adee296d056a4d333" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","goal_id","attempt_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_audit_candidates" ADD CONSTRAINT "fk_dcb8af0664446945dc2f" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_audit_candidates" ADD CONSTRAINT "fk_2344fa551280ad71e3be" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_audit_candidates" ADD CONSTRAINT "fk_2216cbed10dc5b7f2708" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_checkpoints" ADD CONSTRAINT "fk_c8de983b3876e5ebb39e" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_checkpoints" ADD CONSTRAINT "fk_f94fcc9110b2b3daf4b4" FOREIGN KEY ("workspace_id","task_id","parent_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_checkpoints" ADD CONSTRAINT "fk_da56c56d2a80eb863384" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_checkpoints" ADD CONSTRAINT "fk_a6fdd0f4f2a07f7af734" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_checkpoints" ADD CONSTRAINT "fk_a22144fd6ea20a0d7faa" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_command_receipts" ADD CONSTRAINT "fk_097d1f359175c2265c98" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_command_receipts" ADD CONSTRAINT "fk_152cdcc45d79560b69b7" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_6b9e7d1857cdda94bd1b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_dcaa89c9bc74cfbaa3e1" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","goal_id","attempt_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_e71ed344cec06f979ba7" FOREIGN KEY ("workspace_id","task_id","source_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_7bc484cd24921ca88f07" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","audit_id") REFERENCES shiliu."research_outer_audits" ("workspace_id","task_id","goal_id","attempt_id","audit_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_d42938da2478bf239b9e" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_5e8cae4e87041cdd1307" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_compact_improvement_states" ADD CONSTRAINT "fk_51a3f94923c42f5fdf60" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_854f6c8e05703703b4d8" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_539a76b5fcf5cff563bc" FOREIGN KEY ("workspace_id","task_id","goal_id","constraint_id") REFERENCES shiliu."research_constraint_specs" ("workspace_id","task_id","goal_id","constraint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_b3d8692de3b899eed325" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","goal_id","attempt_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_b928ca71fef989e7a3f4" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_4a4a49e1b503dcc100e0" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_c2d29adf57949239b2f4" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_audit_observations" ADD CONSTRAINT "fk_7454052bd0a692a17bd4" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","audit_id") REFERENCES shiliu."research_outer_audits" ("workspace_id","task_id","goal_id","attempt_id","audit_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_specs" ADD CONSTRAINT "fk_36da3d0b703621a2905b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_specs" ADD CONSTRAINT "fk_68074fff952ee86b7e22" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_constraint_specs" ADD CONSTRAINT "fk_9cd04422547f3b59d141" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_ea4beb9d25444cc0f41a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_30fa944681c1316937a2" FOREIGN KEY ("workspace_id","task_id","goal_id","improvement_state_id") REFERENCES shiliu."research_compact_improvement_states" ("workspace_id","task_id","goal_id","improvement_state_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_e8342aaa72fc73d298a6" FOREIGN KEY ("workspace_id","task_id","goal_id","audit_id") REFERENCES shiliu."research_outer_audits" ("workspace_id","task_id","goal_id","audit_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_5e45246184cdbcd441a4" FOREIGN KEY ("workspace_id","task_id","child_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_decd1a6db75338999e52" FOREIGN KEY ("workspace_id","task_id","parent_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_11510dbdb3080426bb55" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_decisions" ADD CONSTRAINT "fk_f1620d647380a57e4437" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_4d7c79d572f795b1858b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_d0b94dedb31fdb685ad9" FOREIGN KEY ("workspace_id","task_id","source_artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_7f233375e062459b5023" FOREIGN KEY ("workspace_id","task_id","source_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_0cc08de67edf5564be30" FOREIGN KEY ("workspace_id","task_id","goal_id","audit_id") REFERENCES shiliu."research_outer_audits" ("workspace_id","task_id","goal_id","audit_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_734aa00f457e401b943a" FOREIGN KEY ("workspace_id","task_id","goal_id","continuation_decision_id") REFERENCES shiliu."research_continuation_decisions" ("workspace_id","task_id","goal_id","continuation_decision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_9c69d1c818c49b11ded4" FOREIGN KEY ("workspace_id","task_id","child_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_4a2cc347d63cb43e706e" FOREIGN KEY ("workspace_id","task_id","parent_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_f0968678fbbd7e281937" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_continuation_seeds" ADD CONSTRAINT "fk_24c9e5f2f44f6ae91c57" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_dispositions" ADD CONSTRAINT "fk_4ac84bf9d6162ad23f7a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_dispositions" ADD CONSTRAINT "fk_89bb244d427e50c5bbbc" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_dispositions" ADD CONSTRAINT "fk_1515f2ddf0b5a73532ef" FOREIGN KEY ("workspace_id","task_id","control_request_id") REFERENCES shiliu."research_control_requests" ("workspace_id","task_id","control_request_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_requests" ADD CONSTRAINT "fk_0db7b680d9f219ed38af" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_requests" ADD CONSTRAINT "fk_710f4d77e59a41cd9c4a" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_requests" ADD CONSTRAINT "fk_d7aa9d886b7591d18d11" FOREIGN KEY ("workspace_id","task_id","expected_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_requests" ADD CONSTRAINT "fk_08d654501166ce2c7298" FOREIGN KEY ("workspace_id","task_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_control_requests" ADD CONSTRAINT "fk_0f81dec9e883eb58e59e" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_events" ADD CONSTRAINT "fk_98e0f2e0e83e39a65bac" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_events" ADD CONSTRAINT "fk_9c5dd6ecb931dd8289a8" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_events" ADD CONSTRAINT "fk_89b6c13d94d600ffdb3e" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_events" ADD CONSTRAINT "fk_75ad9575b6a73d13c684" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_events" ADD CONSTRAINT "fk_390d077d41a526885e59" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_identities" ADD CONSTRAINT "fk_28c09bdfc1755f07f2bf" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_identities" ADD CONSTRAINT "fk_de09a3252f20cce40eb3" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_provenance" ADD CONSTRAINT "fk_3c4e7eb48d6d985d6a21" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_provenance" ADD CONSTRAINT "fk_2b772f1f04b820572f63" FOREIGN KEY ("workspace_id","action_id") REFERENCES shiliu."research_inner_actions" ("workspace_id","action_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_provenance" ADD CONSTRAINT "fk_bb62cd0d634b4bb1ae89" FOREIGN KEY ("workspace_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","evidence_use_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_provenance" ADD CONSTRAINT "fk_e33c49d868c754ddd425" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","task_id","goal_id","attempt_id","evidence_use_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_provenance" ADD CONSTRAINT "fk_b3f6287c5107381f378c" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","action_id") REFERENCES shiliu."research_inner_actions" ("workspace_id","task_id","goal_id","attempt_id","action_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_405c7a563b3557f0d2bb" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_75801f64c19df255fa24" FOREIGN KEY ("workspace_id","task_id","originating_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_8839faea6fcce12b0dab" FOREIGN KEY ("workspace_id","task_id","first_action_id") REFERENCES shiliu."research_inner_actions" ("workspace_id","task_id","action_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_b1d87eb2edd48f8a4466" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_39eef08ff858ea59f5ac" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_69abbad39a4b96ee4c54" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_1b9eefdd5acb9e1bc409" FOREIGN KEY ("workspace_id","evidence_id") REFERENCES shiliu."research_evidence_identities" ("workspace_id","evidence_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_c905ee8eff5df454d462" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","first_action_id") REFERENCES shiliu."research_inner_actions" ("workspace_id","task_id","goal_id","attempt_id","action_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_uses" ADD CONSTRAINT "fk_8aed856108c13f31fee9" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","originating_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_ef3d2a385a818f24e47c" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_5b0d787b971fe163846a" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_dcf2c38a2591d1f06991" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_9e1f4e82b6e295153bba" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_c9904beb6b13e618932e" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_0cde8c54bb47b77db59b" FOREIGN KEY ("workspace_id","evidence_id") REFERENCES shiliu."research_evidence_identities" ("workspace_id","evidence_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_4521ea5b81009b4716c1" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","task_id","goal_id","attempt_id","evidence_use_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_evidence_validations" ADD CONSTRAINT "fk_582c751aaf7c686206bc" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","evidence_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","task_id","goal_id","attempt_id","evidence_id","evidence_use_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_execution_metadata" ADD CONSTRAINT "fk_1d82caf74811457be746" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_execution_metadata" ADD CONSTRAINT "fk_f2e7805c8cc7d0598843" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_417a519b8deab0a4e046" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_bed116cf2695e5d54be5" FOREIGN KEY ("workspace_id","task_id","validation_observation_id") REFERENCES shiliu."research_evidence_validations" ("workspace_id","task_id","observation_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_f2c57ff906d124c650a2" FOREIGN KEY ("workspace_id","task_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","task_id","evidence_use_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_4dee59368316ee15f0ad" FOREIGN KEY ("workspace_id","evidence_id") REFERENCES shiliu."research_evidence_identities" ("workspace_id","evidence_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_ec28b48a0de2c60d1efa" FOREIGN KEY ("workspace_id","task_id","fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_f9d944048126ce419414" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_ed40280ea63f9b4d2bf6" FOREIGN KEY ("workspace_id","task_id","evidence_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","task_id","evidence_id","evidence_use_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_evidence_links" ADD CONSTRAINT "fk_72671af5236e6de3423e" FOREIGN KEY ("workspace_id","task_id","evidence_id","evidence_use_id","validation_observation_id") REFERENCES shiliu."research_evidence_validations" ("workspace_id","task_id","evidence_id","evidence_use_id","observation_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_revisions" ADD CONSTRAINT "fk_07983351f65242103d5a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_revisions" ADD CONSTRAINT "fk_693e633fccbee4a82d6a" FOREIGN KEY ("workspace_id","task_id","origin_candidate_id") REFERENCES shiliu."research_knowledge_candidates" ("workspace_id","task_id","candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_revisions" ADD CONSTRAINT "fk_b34771f5e480b0d7ce3e" FOREIGN KEY ("workspace_id","task_id","supersedes_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_revisions" ADD CONSTRAINT "fk_0619fd0aef2a42bf50c7" FOREIGN KEY ("workspace_id","task_id","parent_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_revisions" ADD CONSTRAINT "fk_c34bcb012e561ff80bbd" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_fact_revisions" ADD CONSTRAINT "fk_b7ba2da67b57d0e81c75" FOREIGN KEY ("workspace_id","task_id","fact_id") REFERENCES shiliu."research_grounded_facts" ("workspace_id","task_id","fact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_goals" ADD CONSTRAINT "fk_7b56910f58d744904523" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_goals" ADD CONSTRAINT "fk_754be5dffd2eafdfe03a" FOREIGN KEY ("workspace_id","task_id","created_by_event_id") REFERENCES shiliu."research_events" ("workspace_id","task_id","event_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_goals" ADD CONSTRAINT "fk_1d02580f0721fa2ffa37" FOREIGN KEY ("workspace_id","task_id","parent_goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_goals" ADD CONSTRAINT "fk_32d2afab5baf3232896e" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_grounded_facts" ADD CONSTRAINT "fk_e3a890ef652f1df45250" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_grounded_facts" ADD CONSTRAINT "fk_80d9c62923804ebe4653" FOREIGN KEY ("workspace_id","task_id","origin_candidate_id") REFERENCES shiliu."research_knowledge_candidates" ("workspace_id","task_id","candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_grounded_facts" ADD CONSTRAINT "fk_a787f5dd32eb01739d9b" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_constraint_observations" ADD CONSTRAINT "fk_978454681f46492884e0" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_constraint_observations" ADD CONSTRAINT "fk_7f4a62b3a023994d47f3" FOREIGN KEY ("workspace_id","task_id","decision_id") REFERENCES shiliu."research_human_decisions" ("workspace_id","task_id","decision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_constraint_observations" ADD CONSTRAINT "fk_7234773adb30c016172d" FOREIGN KEY ("workspace_id","task_id","goal_id","constraint_id") REFERENCES shiliu."research_constraint_specs" ("workspace_id","task_id","goal_id","constraint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_constraint_observations" ADD CONSTRAINT "fk_6dda4ad5ca331d1e742c" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_constraint_observations" ADD CONSTRAINT "fk_55aa72b26c362700ae38" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_constraint_observations" ADD CONSTRAINT "fk_065ef7f333856a4c392b" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_decisions" ADD CONSTRAINT "fk_f180b51b07c8e661b360" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_decisions" ADD CONSTRAINT "fk_827db289f166ff07f7a5" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_decisions" ADD CONSTRAINT "fk_26f8441691ef716df0fc" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_human_decisions" ADD CONSTRAINT "fk_3012955e116051bd8cc7" FOREIGN KEY ("workspace_id","task_id","input_request_id") REFERENCES shiliu."research_input_requests" ("workspace_id","task_id","input_request_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_inner_actions" ADD CONSTRAINT "fk_9194b9964268639543d8" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_inner_actions" ADD CONSTRAINT "fk_7e7d876e2cb02a3607eb" FOREIGN KEY ("workspace_id","task_id","attempt_id","side_effect_id") REFERENCES shiliu."research_side_effects" ("workspace_id","task_id","attempt_id","side_effect_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_inner_actions" ADD CONSTRAINT "fk_02b30bacb5142c183b50" FOREIGN KEY ("workspace_id","task_id","originating_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_inner_actions" ADD CONSTRAINT "fk_db70d63b2d8ca29df1e9" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_inner_actions" ADD CONSTRAINT "fk_68008d0b0f32c27ccbeb" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_inner_actions" ADD CONSTRAINT "fk_00b704c73dfe740e0658" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_dispositions" ADD CONSTRAINT "fk_b3baa122f8ee504f841e" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_dispositions" ADD CONSTRAINT "fk_e6dc579cac7956ec3e64" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_dispositions" ADD CONSTRAINT "fk_f8315d25312a923b0869" FOREIGN KEY ("workspace_id","task_id","input_request_id") REFERENCES shiliu."research_input_requests" ("workspace_id","task_id","input_request_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_requests" ADD CONSTRAINT "fk_ccd5cf99bc18fd37ba1b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_requests" ADD CONSTRAINT "fk_86a88d88990924fbe229" FOREIGN KEY ("workspace_id","task_id","goal_id","constraint_id") REFERENCES shiliu."research_constraint_specs" ("workspace_id","task_id","goal_id","constraint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_requests" ADD CONSTRAINT "fk_5b3b7567b59055b00b73" FOREIGN KEY ("workspace_id","task_id","source_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_requests" ADD CONSTRAINT "fk_98e02545570699958548" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_requests" ADD CONSTRAINT "fk_6f4ce4173fed9d42f629" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_input_requests" ADD CONSTRAINT "fk_9e01e0d6e4c967e9f611" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifact_revisions" ADD CONSTRAINT "fk_e3301fbe92856d77b8fa" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifact_revisions" ADD CONSTRAINT "fk_f46a06c9ff1bccd900ec" FOREIGN KEY ("workspace_id","task_id","supersedes_revision_id") REFERENCES shiliu."research_knowledge_artifact_revisions" ("workspace_id","task_id","artifact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifact_revisions" ADD CONSTRAINT "fk_65198b06f4020c688918" FOREIGN KEY ("workspace_id","task_id","parent_revision_id") REFERENCES shiliu."research_knowledge_artifact_revisions" ("workspace_id","task_id","artifact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifact_revisions" ADD CONSTRAINT "fk_7fbbf623e5419ce21c8a" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifact_revisions" ADD CONSTRAINT "fk_4ab9ff2fa1ec0ca8228f" FOREIGN KEY ("workspace_id","task_id","artifact_id") REFERENCES shiliu."research_knowledge_artifacts" ("workspace_id","task_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifacts" ADD CONSTRAINT "fk_61e577d0305bcbcfa4b1" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_artifacts" ADD CONSTRAINT "fk_3a1bd90b1b2f2c1b5b49" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_build_runs" ADD CONSTRAINT "fk_5207f8aa6b9c526775a4" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_build_runs" ADD CONSTRAINT "fk_d0733ab1e3db65460d1a" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_aeaef02a8c24ef629cb0" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_89dcd84d6902c7754ccb" FOREIGN KEY ("workspace_id","task_id","parent_candidate_id") REFERENCES shiliu."research_knowledge_candidates" ("workspace_id","task_id","candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_18b02514919eac5cfd51" FOREIGN KEY ("workspace_id","task_id","source_event_id") REFERENCES shiliu."research_events" ("workspace_id","task_id","event_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_863b266981c9c60eaf1b" FOREIGN KEY ("workspace_id","task_id","provisional_artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_00d68b7f051591a29297" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","result_id") REFERENCES shiliu."research_results" ("workspace_id","task_id","goal_id","attempt_id","result_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_6fd91180fa4a26e7ac31" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_49ab7846ac7d4907b113" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_1320b22e4ab0db2864c6" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_f9cc2294489af693883f" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_candidates" ADD CONSTRAINT "fk_aa0241091326b4dd97d2" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id","provisional_artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id","artifact_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_conflict_observations" ADD CONSTRAINT "fk_fcd411c95fd62f6c1934" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_conflict_observations" ADD CONSTRAINT "fk_d3ae5832006f1a7cf154" FOREIGN KEY ("workspace_id","task_id","update_candidate_id") REFERENCES shiliu."research_knowledge_update_candidates" ("workspace_id","task_id","update_candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_conflict_observations" ADD CONSTRAINT "fk_e6b8fb1f8bc0104f8fb5" FOREIGN KEY ("workspace_id","task_id","right_fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_conflict_observations" ADD CONSTRAINT "fk_5dd01b17b4563a548039" FOREIGN KEY ("workspace_id","task_id","left_fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_conflict_observations" ADD CONSTRAINT "fk_38466be187d5e736ce35" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_exports" ADD CONSTRAINT "fk_55e29d98a540a6de49f3" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_exports" ADD CONSTRAINT "fk_bfe1ee81c899b1c1082e" FOREIGN KEY ("workspace_id","task_id","operation_id") REFERENCES shiliu."research_knowledge_update_operations" ("workspace_id","task_id","operation_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_exports" ADD CONSTRAINT "fk_ab8600fc192203b10e68" FOREIGN KEY ("workspace_id","task_id","page_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_exports" ADD CONSTRAINT "fk_bcc79f0f13a9b3000d6a" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_fact_states" ADD CONSTRAINT "fk_2af554b413c178c6849f" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_fact_states" ADD CONSTRAINT "fk_25e1e17b0faba99534a6" FOREIGN KEY ("workspace_id","task_id","superseded_by_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_fact_states" ADD CONSTRAINT "fk_719043ed0a6a439564f8" FOREIGN KEY ("workspace_id","task_id","current_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_fact_states" ADD CONSTRAINT "fk_7b7476b671ccaa465366" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_fact_states" ADD CONSTRAINT "fk_3511e7e15bd07c283af0" FOREIGN KEY ("workspace_id","task_id","fact_id") REFERENCES shiliu."research_grounded_facts" ("workspace_id","task_id","fact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_fact_states" ADD CONSTRAINT "fk_2779d7f2ca2b9e527cf2" FOREIGN KEY ("workspace_id","task_id","fact_id","current_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_id","fact_revision_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_01fe246720f3ea20373f" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_2cc9747f5f6aca3c1601" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_25d0a5508b1a6159ab06" FOREIGN KEY ("workspace_id","task_id","related_fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_4f8e2088325369af4133" FOREIGN KEY ("workspace_id","task_id","result_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_25ce2550f66fc6d61843" FOREIGN KEY ("workspace_id","task_id","source_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_8837fae8068d20a9f3f9" FOREIGN KEY ("workspace_id","task_id","update_candidate_id") REFERENCES shiliu."research_knowledge_update_candidates" ("workspace_id","task_id","update_candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_8fd7405906699542d151" FOREIGN KEY ("workspace_id","task_id","fact_id") REFERENCES shiliu."research_grounded_facts" ("workspace_id","task_id","fact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_lifecycle_decisions" ADD CONSTRAINT "fk_ad8ef87fed7de341977f" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_be06cd8acb8e3d25516d" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_4587ef925c7406f36868" FOREIGN KEY ("workspace_id","task_id","validation_observation_id") REFERENCES shiliu."research_evidence_validations" ("workspace_id","task_id","observation_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_f6f0df6ae7df78795579" FOREIGN KEY ("workspace_id","task_id","evidence_use_id") REFERENCES shiliu."research_evidence_uses" ("workspace_id","task_id","evidence_use_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_45ecb7dd6eaf4675bec7" FOREIGN KEY ("workspace_id","evidence_id") REFERENCES shiliu."research_evidence_identities" ("workspace_id","evidence_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_6db710dff451338e9766" FOREIGN KEY ("workspace_id","task_id","fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_b4d101d0a87cddcbf6a5" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_revalidation_observations" ADD CONSTRAINT "fk_d409ee0c2b8ec3e4b287" FOREIGN KEY ("workspace_id","task_id","evidence_id","evidence_use_id","validation_observation_id") REFERENCES shiliu."research_evidence_validations" ("workspace_id","task_id","evidence_id","evidence_use_id","observation_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_review_decisions" ADD CONSTRAINT "fk_ace72503ea864bd0386f" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_review_decisions" ADD CONSTRAINT "fk_7f329330e41f71b55d1b" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_review_decisions" ADD CONSTRAINT "fk_1374d1c46458cb4b629a" FOREIGN KEY ("workspace_id","task_id","fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_review_decisions" ADD CONSTRAINT "fk_f443e0ed5f1e05690334" FOREIGN KEY ("workspace_id","task_id","edited_candidate_id") REFERENCES shiliu."research_knowledge_candidates" ("workspace_id","task_id","candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_review_decisions" ADD CONSTRAINT "fk_e0e026ef1620b27c87b2" FOREIGN KEY ("workspace_id","task_id","candidate_id") REFERENCES shiliu."research_knowledge_candidates" ("workspace_id","task_id","candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_review_decisions" ADD CONSTRAINT "fk_acf3a5feb51b95527c72" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_6f9c8b79ae268c9abd6d" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_7625f1c5d45673fb2d17" FOREIGN KEY ("workspace_id","task_id","parent_candidate_id") REFERENCES shiliu."research_knowledge_update_candidates" ("workspace_id","task_id","update_candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_4b6b57739a188d667106" FOREIGN KEY ("workspace_id","task_id","related_fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_862a7778300d493ee54d" FOREIGN KEY ("workspace_id","task_id","source_fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_ca8396ff61d57a8c5127" FOREIGN KEY ("workspace_id","task_id","fact_id") REFERENCES shiliu."research_grounded_facts" ("workspace_id","task_id","fact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_a67dcbd7b89376b01a8c" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_candidates" ADD CONSTRAINT "fk_442fde5797e4c2ce0083" FOREIGN KEY ("workspace_id","task_id","fact_id","source_fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_id","fact_revision_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_operations" ADD CONSTRAINT "fk_b4f192ea335f9ba6434c" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_knowledge_update_operations" ADD CONSTRAINT "fk_1fbf9f6b0fc7a35c9039" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_d8112ed95378a4e4c62a" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_857651ecbe746dc3850b" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","candidate_id") REFERENCES shiliu."research_audit_candidates" ("workspace_id","task_id","goal_id","attempt_id","candidate_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_d33f2392b9313cede3e1" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","goal_id","attempt_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_7566283f422ed0a9c1e6" FOREIGN KEY ("workspace_id","task_id","source_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_c0eaca862d3d0c2a265e" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_464d5b1003e41070db50" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_audits" ADD CONSTRAINT "fk_ccad66ddc5dc961d826e" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_c087fa5cb8b1c137af07" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_f4861bb5821e3ceda81a" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","artifact_id") REFERENCES shiliu."research_provisional_artifacts" ("workspace_id","task_id","goal_id","attempt_id","artifact_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_1f1b1408d823a8b56b68" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","audit_id") REFERENCES shiliu."research_outer_audits" ("workspace_id","task_id","goal_id","attempt_id","audit_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_fab5ad52340912cdad8d" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_ecff662d23b9b85c5233" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_8f1aa9d4dc752d1c3d0a" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_outer_result_links" ADD CONSTRAINT "fk_a15465fe9332847be4b3" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","result_id") REFERENCES shiliu."research_results" ("workspace_id","task_id","goal_id","attempt_id","result_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_provisional_artifacts" ADD CONSTRAINT "fk_d218229b7a0cb814bff8" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_provisional_artifacts" ADD CONSTRAINT "fk_0c84a7226ff4f8ba5ba0" FOREIGN KEY ("workspace_id","task_id","provider_side_effect_id") REFERENCES shiliu."research_side_effects" ("workspace_id","task_id","side_effect_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_provisional_artifacts" ADD CONSTRAINT "fk_6f86c46261abafe226f9" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_provisional_artifacts" ADD CONSTRAINT "fk_4e166973bed6b944c48f" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_provisional_artifacts" ADD CONSTRAINT "fk_2cb6540844681663b45e" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_provisional_artifacts" ADD CONSTRAINT "fk_9e28f0e0b92853d35123" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_results" ADD CONSTRAINT "fk_94e99ca1ccc67f1df5c3" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_results" ADD CONSTRAINT "fk_2a999d22f18396ff3b1c" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","goal_id","attempt_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_results" ADD CONSTRAINT "fk_0379c0ebc79ae8064969" FOREIGN KEY ("workspace_id","task_id","goal_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","goal_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_results" ADD CONSTRAINT "fk_c5208c13226277686bf7" FOREIGN KEY ("workspace_id","task_id","goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_results" ADD CONSTRAINT "fk_c6ba84d6bbf36b389b13" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effect_resolutions" ADD CONSTRAINT "fk_0731eb2acf3f01a7b2a2" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effect_resolutions" ADD CONSTRAINT "fk_db8247ea3a8f9824a62d" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effect_resolutions" ADD CONSTRAINT "fk_dd96801ff642abb16724" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effect_resolutions" ADD CONSTRAINT "fk_eaba31efa1d75f4eadfd" FOREIGN KEY ("workspace_id","task_id","side_effect_id") REFERENCES shiliu."research_side_effects" ("workspace_id","task_id","side_effect_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effects" ADD CONSTRAINT "fk_3a3983af5e89605477db" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effects" ADD CONSTRAINT "fk_e13773dbc7dc1199400d" FOREIGN KEY ("workspace_id","task_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_side_effects" ADD CONSTRAINT "fk_7f93ba058fd7337573f1" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_60cec5e13bb98e82901d" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_b823495320d0b25fcdec" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_2fbcf292eeba6f3e4cb1" FOREIGN KEY ("workspace_id","child_task_id","child_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_ddb5b26995ec2dbcc18c" FOREIGN KEY ("workspace_id","child_task_id","child_goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_7b5f81b35840a7fca2cb" FOREIGN KEY ("workspace_id","child_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_705b7d2b909e06952583" FOREIGN KEY ("workspace_id","source_task_id","source_checkpoint_id") REFERENCES shiliu."research_checkpoints" ("workspace_id","task_id","checkpoint_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_df17db354916426ccec3" FOREIGN KEY ("workspace_id","source_task_id","source_attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_3f13a75bd84e0eacdd4f" FOREIGN KEY ("workspace_id","source_task_id","source_goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_task_derivations" ADD CONSTRAINT "fk_494d7a79b02592805631" FOREIGN KEY ("workspace_id","source_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_tasks" ADD CONSTRAINT "fk_29a972e3b1cdee72bef2" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_tasks" ADD CONSTRAINT "fk_5e5d0cf2a79ea736027d" FOREIGN KEY ("workspace_id","owner_user_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_tasks" ADD CONSTRAINT "fk_cd71eddafc36d8b90f4d" FOREIGN KEY ("workspace_id","task_id","terminal_result_id") REFERENCES shiliu."research_results" ("workspace_id","task_id","result_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_tasks" ADD CONSTRAINT "fk_d78bb606ccb8146fd321" FOREIGN KEY ("workspace_id","task_id","active_goal_id") REFERENCES shiliu."research_goals" ("workspace_id","task_id","goal_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_tasks" ADD CONSTRAINT "fk_072e48b91d730d034b8a" FOREIGN KEY ("workspace_id","parent_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_fact_links" ADD CONSTRAINT "fk_78fb17cc27fd58dd42fa" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_fact_links" ADD CONSTRAINT "fk_f7fc10a3758a8312c95a" FOREIGN KEY ("workspace_id","task_id","fact_revision_id") REFERENCES shiliu."research_fact_revisions" ("workspace_id","task_id","fact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_fact_links" ADD CONSTRAINT "fk_c01ffb715ab2c0b3f3e3" FOREIGN KEY ("workspace_id","task_id","page_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_fact_links" ADD CONSTRAINT "fk_31e70f2385d10af3eb47" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_review_decisions" ADD CONSTRAINT "fk_a3f29a1e07f3f689d3e6" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_review_decisions" ADD CONSTRAINT "fk_b2adfe9219b9fed6aac6" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_review_decisions" ADD CONSTRAINT "fk_688d6469bbd87dd0daa0" FOREIGN KEY ("workspace_id","task_id","page_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_review_decisions" ADD CONSTRAINT "fk_48c0545b4d56e94740bd" FOREIGN KEY ("workspace_id","task_id","page_id") REFERENCES shiliu."research_topic_pages" ("workspace_id","task_id","page_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_review_decisions" ADD CONSTRAINT "fk_611775696954234b0ab7" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_c89b43e064cd298b7f1b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_259b2225c8424665ef53" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_420f7c6c4d7d1c908761" FOREIGN KEY ("workspace_id","task_id","result_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_1950740862a79adaf05d" FOREIGN KEY ("workspace_id","task_id","source_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_9aa1366deef05f510934" FOREIGN KEY ("workspace_id","task_id","page_id") REFERENCES shiliu."research_topic_pages" ("workspace_id","task_id","page_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_558a8d6d85b913cbf5c7" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_f7bde8606958e49be5a5" FOREIGN KEY ("workspace_id","task_id","page_id","source_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_id","page_revision_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revision_decisions" ADD CONSTRAINT "fk_6363b3fa76bb27e5c25e" FOREIGN KEY ("workspace_id","task_id","page_id","result_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_id","page_revision_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_f4c472f6e6d212b639e0" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_986a60c79d432da39c34" FOREIGN KEY ("workspace_id","task_id","artifact_revision_id") REFERENCES shiliu."research_knowledge_artifact_revisions" ("workspace_id","task_id","artifact_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_f3c0477d1e4a599cd7cb" FOREIGN KEY ("workspace_id","task_id","revert_of_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_bc79790045262d557a99" FOREIGN KEY ("workspace_id","task_id","supersedes_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_dcd83ba36aa18022fbfd" FOREIGN KEY ("workspace_id","task_id","parent_revision_id") REFERENCES shiliu."research_topic_page_revisions" ("workspace_id","task_id","page_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_e15a94abc348ff444b74" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_page_revisions" ADD CONSTRAINT "fk_2cc6f901838b61496683" FOREIGN KEY ("workspace_id","task_id","page_id") REFERENCES shiliu."research_topic_pages" ("workspace_id","task_id","page_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_pages" ADD CONSTRAINT "fk_36e2cb65bf74366839e6" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_topic_pages" ADD CONSTRAINT "fk_b4fcdf9c6cacb891f79d" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_traces" ADD CONSTRAINT "fk_08187d6e2523df34c8ab" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_traces" ADD CONSTRAINT "fk_ce71fc71012676500d90" FOREIGN KEY ("workspace_id","task_id","attempt_id") REFERENCES shiliu."research_attempts" ("workspace_id","task_id","attempt_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_traces" ADD CONSTRAINT "fk_f1f5ae1b0cf41f5dcf7f" FOREIGN KEY ("workspace_id","task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_workspace_records" ADD CONSTRAINT "fk_5ad159cd0378dceda70d" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_workspace_records" ADD CONSTRAINT "fk_ddb749681b862290c463" FOREIGN KEY ("principal_id") REFERENCES shiliu."users" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_workspace_records" ADD CONSTRAINT "fk_ac4561227e1ac257d60f" FOREIGN KEY ("workspace_id","command_task_id") REFERENCES shiliu."research_tasks" ("workspace_id","task_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."research_workspace_records" ADD CONSTRAINT "fk_1d54fef5eb1a95273832" FOREIGN KEY ("workspace_id","parent_revision_id") REFERENCES shiliu."research_workspace_records" ("workspace_id","record_revision_id") ON DELETE RESTRICT DEFERRABLE INITIALLY IMMEDIATE;

CREATE FUNCTION shiliu.reject_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'immutable_record' USING ERRCODE='23514'; END $$;

CREATE TRIGGER "trg_knowledge_draft_revisions_no_delete" BEFORE DELETE ON shiliu."knowledge_draft_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_knowledge_draft_revisions_no_update" BEFORE UPDATE ON shiliu."knowledge_draft_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_artifact_fact_link_no_delete" BEFORE DELETE ON shiliu."research_artifact_fact_links" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_artifact_fact_link_no_update" BEFORE UPDATE ON shiliu."research_artifact_fact_links" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_artifact_routes_immutable_delete" BEFORE DELETE ON shiliu."research_artifact_routes" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_artifact_routes_immutable_update" BEFORE UPDATE ON shiliu."research_artifact_routes" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_improvement_state_no_delete" BEFORE DELETE ON shiliu."research_compact_improvement_states" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_improvement_state_no_update" BEFORE UPDATE ON shiliu."research_compact_improvement_states" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_constraint_observation_no_delete" BEFORE DELETE ON shiliu."research_constraint_audit_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_constraint_observation_no_update" BEFORE UPDATE ON shiliu."research_constraint_audit_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_constraint_spec_no_delete" BEFORE DELETE ON shiliu."research_constraint_specs" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_constraint_spec_no_update" BEFORE UPDATE ON shiliu."research_constraint_specs" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_continuation_seed_no_delete" BEFORE DELETE ON shiliu."research_continuation_seeds" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_continuation_seed_no_update" BEFORE UPDATE ON shiliu."research_continuation_seeds" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_control_disposition_no_delete" BEFORE DELETE ON shiliu."research_control_dispositions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_control_disposition_no_update" BEFORE UPDATE ON shiliu."research_control_dispositions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_control_request_no_delete" BEFORE DELETE ON shiliu."research_control_requests" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_control_request_no_update" BEFORE UPDATE ON shiliu."research_control_requests" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_candidate_delta_event_no_delete" BEFORE DELETE ON shiliu."research_events" FOR EACH ROW WHEN (OLD.event_type='candidate_deltas_materialized') EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_candidate_delta_event_no_update" BEFORE UPDATE ON shiliu."research_events" FOR EACH ROW WHEN (OLD.event_type='candidate_deltas_materialized' OR NEW.event_type='candidate_deltas_materialized') EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_identity_no_delete" BEFORE DELETE ON shiliu."research_evidence_identities" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_identity_no_update" BEFORE UPDATE ON shiliu."research_evidence_identities" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_provenance_no_delete" BEFORE DELETE ON shiliu."research_evidence_provenance" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_provenance_no_update" BEFORE UPDATE ON shiliu."research_evidence_provenance" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_use_no_delete" BEFORE DELETE ON shiliu."research_evidence_uses" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_use_no_update" BEFORE UPDATE ON shiliu."research_evidence_uses" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_validation_no_delete" BEFORE DELETE ON shiliu."research_evidence_validations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_evidence_validation_no_update" BEFORE UPDATE ON shiliu."research_evidence_validations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_fact_evidence_link_no_delete" BEFORE DELETE ON shiliu."research_fact_evidence_links" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_fact_evidence_link_no_update" BEFORE UPDATE ON shiliu."research_fact_evidence_links" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_fact_revision_no_delete" BEFORE DELETE ON shiliu."research_fact_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_fact_revision_no_update" BEFORE UPDATE ON shiliu."research_fact_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_grounded_fact_no_delete" BEFORE DELETE ON shiliu."research_grounded_facts" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_grounded_fact_no_update" BEFORE UPDATE ON shiliu."research_grounded_facts" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_human_constraint_observation_no_delete" BEFORE DELETE ON shiliu."research_human_constraint_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_human_constraint_observation_no_update" BEFORE UPDATE ON shiliu."research_human_constraint_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_human_decision_no_delete" BEFORE DELETE ON shiliu."research_human_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_human_decision_no_update" BEFORE UPDATE ON shiliu."research_human_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_input_disposition_no_delete" BEFORE DELETE ON shiliu."research_input_dispositions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_input_disposition_no_update" BEFORE UPDATE ON shiliu."research_input_dispositions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_input_request_no_delete" BEFORE DELETE ON shiliu."research_input_requests" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_input_request_no_update" BEFORE UPDATE ON shiliu."research_input_requests" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_artifact_revision_no_delete" BEFORE DELETE ON shiliu."research_knowledge_artifact_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_artifact_revision_no_update" BEFORE UPDATE ON shiliu."research_knowledge_artifact_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_artifact_no_delete" BEFORE DELETE ON shiliu."research_knowledge_artifacts" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_artifact_no_update" BEFORE UPDATE ON shiliu."research_knowledge_artifacts" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_build_identity_no_update" BEFORE UPDATE ON shiliu."research_knowledge_build_runs" FOR EACH ROW WHEN (NEW.build_run_id IS DISTINCT FROM OLD.build_run_id OR NEW.workspace_schema_version IS DISTINCT FROM OLD.workspace_schema_version OR NEW.task_id IS DISTINCT FROM OLD.task_id OR NEW.build_kind IS DISTINCT FROM OLD.build_kind OR NEW.command_id IS DISTINCT FROM OLD.command_id OR NEW.input_hash IS DISTINCT FROM OLD.input_hash OR NEW.input_json IS DISTINCT FROM OLD.input_json OR NEW.created_at IS DISTINCT FROM OLD.created_at) EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_build_no_delete" BEFORE DELETE ON shiliu."research_knowledge_build_runs" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_candidate_lineage_no_update" BEFORE UPDATE ON shiliu."research_knowledge_candidates" FOR EACH ROW WHEN (NEW.candidate_id IS DISTINCT FROM OLD.candidate_id OR NEW.workspace_schema_version IS DISTINCT FROM OLD.workspace_schema_version OR NEW.task_id IS DISTINCT FROM OLD.task_id OR NEW.goal_id IS DISTINCT FROM OLD.goal_id OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id OR NEW.checkpoint_id IS DISTINCT FROM OLD.checkpoint_id OR NEW.result_id IS DISTINCT FROM OLD.result_id OR NEW.provisional_artifact_id IS DISTINCT FROM OLD.provisional_artifact_id OR NEW.source_event_id IS DISTINCT FROM OLD.source_event_id OR NEW.source_delta_snapshot_id IS DISTINCT FROM OLD.source_delta_snapshot_id OR NEW.candidate_kind IS DISTINCT FROM OLD.candidate_kind OR NEW.source_boundary_hash IS DISTINCT FROM OLD.source_boundary_hash OR NEW.source_delta_hash IS DISTINCT FROM OLD.source_delta_hash OR NEW.source_item_hash IS DISTINCT FROM OLD.source_item_hash OR NEW.source_item_index IS DISTINCT FROM OLD.source_item_index OR NEW.parent_candidate_id IS DISTINCT FROM OLD.parent_candidate_id OR NEW.claim_text IS DISTINCT FROM OLD.claim_text OR NEW.citation_ids_json IS DISTINCT FROM OLD.citation_ids_json OR NEW.evidence_use_ids_json IS DISTINCT FROM OLD.evidence_use_ids_json OR NEW.source_payload_json IS DISTINCT FROM OLD.source_payload_json OR NEW.created_at IS DISTINCT FROM OLD.created_at) EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_candidate_no_delete" BEFORE DELETE ON shiliu."research_knowledge_candidates" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_conflict_no_delete" BEFORE DELETE ON shiliu."research_knowledge_conflict_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_conflict_no_update" BEFORE UPDATE ON shiliu."research_knowledge_conflict_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_export_no_delete" BEFORE DELETE ON shiliu."research_knowledge_exports" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_export_no_update" BEFORE UPDATE ON shiliu."research_knowledge_exports" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_fact_state_identity_no_update" BEFORE UPDATE ON shiliu."research_knowledge_fact_states" FOR EACH ROW WHEN (NEW.fact_id IS DISTINCT FROM OLD.fact_id OR NEW.task_id IS DISTINCT FROM OLD.task_id) EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_fact_state_no_delete" BEFORE DELETE ON shiliu."research_knowledge_fact_states" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_lifecycle_decision_no_delete" BEFORE DELETE ON shiliu."research_knowledge_lifecycle_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_lifecycle_decision_no_update" BEFORE UPDATE ON shiliu."research_knowledge_lifecycle_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_revalidation_no_delete" BEFORE DELETE ON shiliu."research_knowledge_revalidation_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_revalidation_no_update" BEFORE UPDATE ON shiliu."research_knowledge_revalidation_observations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_decision_no_delete" BEFORE DELETE ON shiliu."research_knowledge_review_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_decision_no_update" BEFORE UPDATE ON shiliu."research_knowledge_review_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_update_candidate_lineage_no_update" BEFORE UPDATE ON shiliu."research_knowledge_update_candidates" FOR EACH ROW WHEN (NEW.update_candidate_id IS DISTINCT FROM OLD.update_candidate_id OR NEW.task_id IS DISTINCT FROM OLD.task_id OR NEW.fact_id IS DISTINCT FROM OLD.fact_id OR NEW.source_fact_revision_id IS DISTINCT FROM OLD.source_fact_revision_id OR NEW.related_fact_revision_id IS DISTINCT FROM OLD.related_fact_revision_id OR NEW.source_observation_set_id IS DISTINCT FROM OLD.source_observation_set_id OR NEW.candidate_kind IS DISTINCT FROM OLD.candidate_kind OR NEW.proposed_claim IS DISTINCT FROM OLD.proposed_claim OR NEW.temporal_scope_json IS DISTINCT FROM OLD.temporal_scope_json OR NEW.viewpoint_scope_json IS DISTINCT FROM OLD.viewpoint_scope_json OR NEW.evidence_use_ids_json IS DISTINCT FROM OLD.evidence_use_ids_json OR NEW.affected_artifact_ids_json IS DISTINCT FROM OLD.affected_artifact_ids_json OR NEW.affected_page_ids_json IS DISTINCT FROM OLD.affected_page_ids_json OR NEW.validator_status IS DISTINCT FROM OLD.validator_status OR NEW.parent_candidate_id IS DISTINCT FROM OLD.parent_candidate_id OR NEW.created_at IS DISTINCT FROM OLD.created_at) EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_update_candidate_no_delete" BEFORE DELETE ON shiliu."research_knowledge_update_candidates" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_operation_identity_no_update" BEFORE UPDATE ON shiliu."research_knowledge_update_operations" FOR EACH ROW WHEN (NEW.operation_id IS DISTINCT FROM OLD.operation_id OR NEW.task_id IS DISTINCT FROM OLD.task_id OR NEW.operation_kind IS DISTINCT FROM OLD.operation_kind OR NEW.target_reference IS DISTINCT FROM OLD.target_reference OR NEW.dedup_key IS DISTINCT FROM OLD.dedup_key OR NEW.command_id IS DISTINCT FROM OLD.command_id OR NEW.input_hash IS DISTINCT FROM OLD.input_hash OR NEW.input_json IS DISTINCT FROM OLD.input_json OR NEW.expected_heads_json IS DISTINCT FROM OLD.expected_heads_json OR NEW.max_attempts IS DISTINCT FROM OLD.max_attempts OR NEW.created_at IS DISTINCT FROM OLD.created_at) EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_knowledge_operation_no_delete" BEFORE DELETE ON shiliu."research_knowledge_update_operations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_outer_audit_no_delete" BEFORE DELETE ON shiliu."research_outer_audits" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_outer_audit_no_update" BEFORE UPDATE ON shiliu."research_outer_audits" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_provisional_artifact_no_delete" BEFORE DELETE ON shiliu."research_provisional_artifacts" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_provisional_artifact_no_update" BEFORE UPDATE ON shiliu."research_provisional_artifacts" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_side_effect_resolution_no_delete" BEFORE DELETE ON shiliu."research_side_effect_resolutions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_side_effect_resolution_no_update" BEFORE UPDATE ON shiliu."research_side_effect_resolutions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_task_derivation_no_delete" BEFORE DELETE ON shiliu."research_task_derivations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_task_derivation_no_update" BEFORE UPDATE ON shiliu."research_task_derivations" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_fact_link_no_delete" BEFORE DELETE ON shiliu."research_topic_page_fact_links" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_fact_link_no_update" BEFORE UPDATE ON shiliu."research_topic_page_fact_links" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_review_no_delete" BEFORE DELETE ON shiliu."research_topic_page_review_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_review_no_update" BEFORE UPDATE ON shiliu."research_topic_page_review_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_page_revision_decision_no_delete" BEFORE DELETE ON shiliu."research_topic_page_revision_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_page_revision_decision_no_update" BEFORE UPDATE ON shiliu."research_topic_page_revision_decisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_revision_no_delete" BEFORE DELETE ON shiliu."research_topic_page_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_revision_no_update" BEFORE UPDATE ON shiliu."research_topic_page_revisions" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_identity_no_update" BEFORE UPDATE ON shiliu."research_topic_pages" FOR EACH ROW WHEN (NEW.page_id IS DISTINCT FROM OLD.page_id OR NEW.workspace_schema_version IS DISTINCT FROM OLD.workspace_schema_version OR NEW.task_id IS DISTINCT FROM OLD.task_id OR NEW.slug IS DISTINCT FROM OLD.slug OR NEW.created_at IS DISTINCT FROM OLD.created_at) EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_topic_page_no_delete" BEFORE DELETE ON shiliu."research_topic_pages" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_workspace_records_immutable_delete" BEFORE DELETE ON shiliu."research_workspace_records" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "trg_research_workspace_records_immutable_update" BEFORE UPDATE ON shiliu."research_workspace_records" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();
