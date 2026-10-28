CREATE TABLE shiliu."retrieval_dense_index_meta" (
    "index_name" text NOT NULL,
    "dense_index_version" text NOT NULL,
    "model_id" text NOT NULL,
    "embedding_dimension" bigint NOT NULL,
    "embedding_dtype" text NOT NULL,
    "normalized" boolean NOT NULL,
    "projection_version" text NOT NULL,
    "total_unit_count" bigint NOT NULL,
    "video_unit_count" bigint NOT NULL,
    "chunk_unit_count" bigint NOT NULL,
    "built_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "build_duration_seconds" double precision NOT NULL,
    "model_revision" text NOT NULL DEFAULT '46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59',
    "provider_version" text NOT NULL DEFAULT 'v3-fastembed-bge-provider-v1',
    "embedding_mode" text NOT NULL DEFAULT 'fastembed-normalized-512',
    "query_instruction_version" text NOT NULL DEFAULT 'none',
    "input_policy_version" text NOT NULL DEFAULT 'v3-bge-input-512-v1',
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("workspace_id","index_name")
);

CREATE TABLE shiliu."retrieval_index_meta" (
    "index_name" text NOT NULL,
    "index_version" text NOT NULL,
    "tokenizer" text NOT NULL,
    "rebuilt_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    "eligible_video_count" bigint NOT NULL,
    "video_unit_count" bigint NOT NULL,
    "chunk_unit_count" bigint NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("workspace_id","index_name")
);

CREATE TABLE shiliu."retrieval_search_presentations" (
    "trace_id" text NOT NULL,
    "presentation_version" text NOT NULL,
    "consolidation_version" text NOT NULL,
    "jump_anchor_version" text NOT NULL,
    "chapter_enrichment_version" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "requested_result_limit" bigint NOT NULL,
    "max_windows_per_video" bigint NOT NULL,
    "raw_top_k" bigint NOT NULL,
    "merge_gap_seconds" double precision NOT NULL,
    "raw_hit_count" bigint NOT NULL,
    "unique_video_count" bigint NOT NULL,
    "duplicate_raw_hit_count" bigint NOT NULL,
    "duplicate_occupancy_count" bigint NOT NULL,
    "duplicate_occupancy_rate" double precision NOT NULL,
    "group_count_before_limit" bigint NOT NULL,
    "returned_group_count" bigint NOT NULL,
    "total_window_count" bigint NOT NULL,
    "returned_window_count" bigint NOT NULL,
    "anchored_window_count" bigint NOT NULL,
    "chapter_enriched_count" bigint NOT NULL,
    "grouping_ms" double precision NOT NULL,
    "anchor_ms" double precision NOT NULL,
    "chapter_ms" double precision NOT NULL,
    "presentation_total_ms" double precision NOT NULL,
    "presentation_trace_ms" double precision NOT NULL DEFAULT 0,
    "status" text NOT NULL,
    "error_stage" text,
    "error_message" text,
    "group_summary_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "product_default_wiring_version" text,
    "requested_mode" text,
    "default_applied" boolean NOT NULL DEFAULT false,
    "configured_default_mode" text,
    "router_invoked" boolean NOT NULL DEFAULT false,
    "router_version" text,
    "router_decision" text,
    "effective_mode" text,
    "router_reason_codes_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "embedding_invoked" boolean NOT NULL DEFAULT false,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("trace_id")
);

CREATE INDEX "idx_retrieval_presentations_created" ON shiliu."retrieval_search_presentations" ("workspace_id", "created_at" DESC, "trace_id");

CREATE TABLE shiliu."retrieval_search_traces" (
    "trace_id" text NOT NULL,
    "trace_version" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    "raw_query" text NOT NULL,
    "normalized_query" text,
    "query_type" text,
    "requested_mode" text NOT NULL,
    "planned_mode" text,
    "executed_mode" text,
    "routing_reason" text,
    "scope" text NOT NULL,
    "filters_json" jsonb NOT NULL,
    "raw_top_k" bigint NOT NULL,
    "lexical_candidate_count" bigint NOT NULL DEFAULT 0,
    "dense_candidate_count" bigint NOT NULL DEFAULT 0,
    "raw_hit_count" bigint NOT NULL DEFAULT 0,
    "planning_ms" double precision NOT NULL DEFAULT 0,
    "lexical_ms" double precision NOT NULL DEFAULT 0,
    "dense_ms" double precision NOT NULL DEFAULT 0,
    "fusion_ms" double precision NOT NULL DEFAULT 0,
    "total_ms" double precision NOT NULL DEFAULT 0,
    "lexical_index_version" text,
    "dense_index_version" text,
    "model_id" text,
    "model_revision" text,
    "provider_version" text,
    "projection_version" text,
    "query_instruction_version" text,
    "input_policy_version" text,
    "fusion_version" text,
    "fallback" boolean NOT NULL DEFAULT false,
    "fallback_reason" text,
    "status" text NOT NULL,
    "error_code" text,
    "error_stage" text,
    "error_message" text,
    "raw_hits_json" jsonb NOT NULL DEFAULT '[]'::jsonb,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("trace_id"),
    UNIQUE ("workspace_id","trace_id")
);

CREATE INDEX "idx_retrieval_search_traces_created" ON shiliu."retrieval_search_traces" ("workspace_id", "created_at" DESC, "trace_id");

CREATE TABLE shiliu."retrieval_sync_state" (
    "video_id" bigint NOT NULL,
    "sync_state_version" text NOT NULL,
    "desired_state" text NOT NULL,
    "lexical_state" text NOT NULL,
    "dense_state" text NOT NULL,
    "last_trigger" text NOT NULL,
    "last_attempt_at" timestamptz NOT NULL,
    "last_success_at" timestamptz,
    "last_error_stage" text,
    "last_error_message" text,
    "updated_at" timestamptz NOT NULL,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("video_id"),
    CHECK (desired_state IN ('indexed', 'absent'))
);

CREATE INDEX "idx_retrieval_sync_failure" ON shiliu."retrieval_sync_state" ("workspace_id", "lexical_state", "dense_state", "video_id");

CREATE TABLE shiliu."retrieval_unit_folders" (
    "unit_id" text NOT NULL,
    "source_db_id" bigint NOT NULL,
    "folder_id" bigint NOT NULL,
    "folder_title" text NOT NULL,
    "favorite_time" bigint,
    "workspace_id" text NOT NULL,
    PRIMARY KEY ("unit_id","source_db_id")
);

CREATE INDEX "idx_retrieval_folders_filter" ON shiliu."retrieval_unit_folders" ("workspace_id", "source_db_id", "folder_id", "favorite_time", "unit_id");

CREATE TABLE shiliu."retrieval_units" (
    "unit_id" text NOT NULL,
    "unit_type" text NOT NULL,
    "video_id" bigint NOT NULL,
    "platform" text NOT NULL,
    "source_id" text NOT NULL,
    "part" bigint NOT NULL,
    "title" text NOT NULL,
    "uploader" text NOT NULL,
    "chunk_id" text,
    "source_type" text NOT NULL,
    "start_time" double precision,
    "end_time" double precision,
    "source_text" text NOT NULL,
    "search_text" text NOT NULL,
    "content_hash" text NOT NULL,
    "index_version" text NOT NULL,
    "reading_state" text NOT NULL,
    "is_marked" boolean NOT NULL,
    "is_ignored" boolean NOT NULL,
    "archived_at" timestamptz,
    "removed_at" timestamptz,
    "workspace_id" text NOT NULL,
    "tokenized_text" text NOT NULL DEFAULT '',
    "search_vector" tsvector NOT NULL DEFAULT ''::tsvector,
    "generation" bigint NOT NULL DEFAULT 0,
    PRIMARY KEY ("unit_id"),
    UNIQUE ("video_id","chunk_id"),
    UNIQUE ("workspace_id","unit_id"),
    CHECK (unit_type IN ('video', 'transcript_chunk')),
    CHECK ((unit_type='video' AND chunk_id IS NULL AND start_time IS NULL AND end_time IS NULL) OR (unit_type='transcript_chunk' AND chunk_id IS NOT NULL AND start_time IS NOT NULL AND end_time IS NOT NULL))
);

CREATE INDEX "idx_retrieval_units_video" ON shiliu."retrieval_units" ("workspace_id", "video_id", "unit_type");

CREATE INDEX "idx_retrieval_units_visibility" ON shiliu."retrieval_units" ("workspace_id", "unit_type", "is_ignored", "archived_at");

CREATE INDEX "retrieval_units_fts_gin" ON shiliu."retrieval_units" USING GIN(search_vector);

CREATE TABLE shiliu."scheduler_lanes" (
    "workspace_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "lane" text NOT NULL,
    "active_job_id" text,
    "lease_epoch" bigint NOT NULL DEFAULT 0,
    "lease_until" timestamptz,
    PRIMARY KEY ("workspace_id","principal_id","lane")
);

CREATE TABLE shiliu."artifact_objects" (
    "workspace_id" text NOT NULL,
    "sha256" text NOT NULL,
    "relative_key" text NOT NULL,
    "byte_size" bigint NOT NULL,
    "media_type" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    PRIMARY KEY ("workspace_id","sha256"),
    UNIQUE ("workspace_id","relative_key"),
    CHECK (byte_size>=0),
    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (relative_key NOT LIKE '/%' AND relative_key !~ '(^|/)\.\.(/|$)' AND relative_key LIKE workspace_id||'/%')
);

CREATE TABLE shiliu."artifact_versions" (
    "id" text NOT NULL,
    "workspace_id" text NOT NULL,
    "video_id" bigint,
    "logical_key" text NOT NULL,
    "source_version" text NOT NULL,
    "object_sha256" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("workspace_id","logical_key","source_version"),
    UNIQUE ("workspace_id","logical_key","id")
);

CREATE TABLE shiliu."artifact_heads" (
    "workspace_id" text NOT NULL,
    "logical_key" text NOT NULL,
    "artifact_version_id" text NOT NULL,
    PRIMARY KEY ("workspace_id","logical_key")
);

CREATE TABLE shiliu."retrieval_projection_tasks" (
    "id" bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
    "workspace_id" text NOT NULL,
    "domain" text NOT NULL,
    "resource_key" text NOT NULL,
    "requested_generation" bigint NOT NULL,
    "payload" jsonb NOT NULL,
    "status" text NOT NULL DEFAULT 'queued',
    "attempt" bigint NOT NULL DEFAULT 0,
    "not_before" timestamptz NOT NULL,
    "lease_owner" text,
    "lease_epoch" bigint NOT NULL DEFAULT 0,
    "lease_until" timestamptz,
    "last_error" text,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("workspace_id","domain","resource_key"),
    CHECK (domain IN ('collection','wiki')),
    CHECK (status IN ('queued','running','retry_wait','completed','failed')),
    CHECK (attempt>=0),
    CHECK (lease_epoch>=0)
);

CREATE TABLE shiliu."model_dispatch_receipts" (
    "workspace_id" text NOT NULL,
    "principal_id" text NOT NULL,
    "dispatch_id" text NOT NULL,
    "run_id" text,
    "job_id" text,
    "lane" text NOT NULL,
    "budget_day" date NOT NULL,
    "status" text NOT NULL,
    "reserved_requests" bigint NOT NULL,
    "usage" jsonb,
    "created_at" timestamptz NOT NULL,
    "settled_at" timestamptz,
    PRIMARY KEY ("workspace_id","principal_id","dispatch_id"),
    CHECK (status IN ('reserved','settled','unknown')),
    CHECK (reserved_requests>=0)
);

CREATE TABLE shiliu."embedding_profiles" (
    "profile_id" text NOT NULL,
    "model_id" text NOT NULL,
    "model_revision" text NOT NULL,
    "dimension" integer NOT NULL,
    "dtype" text NOT NULL,
    "normalized" boolean NOT NULL,
    "provider_version" text NOT NULL,
    "document_policy_version" text NOT NULL,
    "tokenizer_revision" text NOT NULL,
    "max_tokens" integer NOT NULL,
    "identity" jsonb NOT NULL,
    PRIMARY KEY ("profile_id"),
    CHECK (dimension=512),
    CHECK (dtype='float32'),
    CHECK (normalized),
    CHECK (max_tokens=512)
);

CREATE TABLE shiliu."collection_embeddings" (
    "unit_id" text NOT NULL,
    "profile_id" text NOT NULL,
    "workspace_id" text NOT NULL,
    "source_content_hash" text NOT NULL,
    "embedding_text_hash" text NOT NULL,
    "generation" bigint NOT NULL,
    "embedding" shiliu.vector(512) NOT NULL,
    "created_at" timestamptz NOT NULL,
    "updated_at" timestamptz NOT NULL,
    PRIMARY KEY ("unit_id","profile_id")
);

CREATE TABLE shiliu."memory_embeddings" (
    "memory_id" text NOT NULL,
    "profile_id" text NOT NULL,
    "workspace_id" text NOT NULL,
    "memory_version" bigint NOT NULL,
    "change_epoch" bigint NOT NULL,
    "embedding_text_hash" text NOT NULL,
    "embedding" shiliu.vector(512) NOT NULL,
    "updated_at" timestamptz NOT NULL,
    PRIMARY KEY ("memory_id","profile_id")
);

CREATE TABLE shiliu."wiki_windows" (
    "window_id" text NOT NULL,
    "workspace_id" text NOT NULL,
    "page_id" text NOT NULL,
    "block_id" text NOT NULL,
    "page_version" bigint NOT NULL,
    "projection_hash" text NOT NULL,
    "window_no" integer NOT NULL,
    "text" text NOT NULL,
    "tokenized_text" text NOT NULL,
    "search_vector" tsvector NOT NULL,
    "dependency_versions" jsonb NOT NULL,
    "created_at" timestamptz NOT NULL,
    PRIMARY KEY ("window_id"),
    UNIQUE ("page_id","block_id","projection_hash","window_no")
);

CREATE INDEX "wiki_windows_fts_gin" ON shiliu."wiki_windows" USING GIN(search_vector);

CREATE TABLE shiliu."wiki_embeddings" (
    "window_id" text NOT NULL,
    "profile_id" text NOT NULL,
    "embedding_text_hash" text NOT NULL,
    "embedding" shiliu.vector(512) NOT NULL,
    "updated_at" timestamptz NOT NULL,
    PRIMARY KEY ("window_id","profile_id")
);

CREATE TABLE shiliu."migration_runs" (
    "run_id" text NOT NULL,
    "source_manifest_hash" text NOT NULL,
    "source_head" text NOT NULL,
    "source_schema_version" bigint NOT NULL,
    "target_revision" text NOT NULL,
    "mapping_version" text NOT NULL,
    "tool_version" text NOT NULL,
    "status" text NOT NULL,
    "started_at" timestamptz NOT NULL,
    "completed_at" timestamptz,
    PRIMARY KEY ("run_id"),
    CHECK (status IN ('inspected','planned','importing','imported','validating','ready'))
);

CREATE TABLE shiliu."migration_batches" (
    "run_id" text NOT NULL,
    "table_name" text NOT NULL,
    "batch_key" text NOT NULL,
    "input_hash" text NOT NULL,
    "input_rows" bigint NOT NULL,
    "target_rows" bigint NOT NULL,
    "completed_at" timestamptz NOT NULL,
    PRIMARY KEY ("run_id","table_name","batch_key")
);

CREATE TABLE shiliu."migration_exceptions" (
    "run_id" text NOT NULL,
    "table_name" text NOT NULL,
    "record_key" jsonb NOT NULL,
    "category" text NOT NULL,
    "disposition" text NOT NULL,
    "created_at" timestamptz NOT NULL,
    PRIMARY KEY ("run_id","table_name","record_key","category")
);

ALTER TABLE shiliu."ask_search_trace_links" ADD CONSTRAINT "fk_32fea61cd2ecaadf9fae" FOREIGN KEY ("workspace_id","search_trace_id") REFERENCES shiliu."retrieval_search_traces" ("workspace_id","trace_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."assistant_runtime_state" ADD CONSTRAINT "fk_0aabd25cdc719443ba36" FOREIGN KEY ("embedding_profile_id") REFERENCES shiliu."embedding_profiles" ("profile_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_dense_index_meta" ADD CONSTRAINT "fk_a6a244cf2c0e103778fe" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_index_meta" ADD CONSTRAINT "fk_9138fdc2b01037c90dd2" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_search_presentations" ADD CONSTRAINT "fk_49bd4308de5399b50c0b" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_search_presentations" ADD CONSTRAINT "fk_60e07d1fefcb1b0e74c6" FOREIGN KEY ("workspace_id","trace_id") REFERENCES shiliu."retrieval_search_traces" ("workspace_id","trace_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_search_traces" ADD CONSTRAINT "fk_32e4e4de1d8680d4dc10" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_sync_state" ADD CONSTRAINT "fk_35b675858bebc963e5f7" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_sync_state" ADD CONSTRAINT "fk_4a5ec149487c0aeeba5f" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_unit_folders" ADD CONSTRAINT "fk_72d50cdeb25ab452cdf4" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_unit_folders" ADD CONSTRAINT "fk_1236dd110232477e44d4" FOREIGN KEY ("workspace_id","source_db_id") REFERENCES shiliu."favorite_sources" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_unit_folders" ADD CONSTRAINT "fk_ca2bae9c41a3ae865919" FOREIGN KEY ("workspace_id","unit_id") REFERENCES shiliu."retrieval_units" ("workspace_id","unit_id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_units" ADD CONSTRAINT "fk_350b1c6ebd3697ee842d" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_units" ADD CONSTRAINT "fk_f03bdf002b8ad0a62d22" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."scheduler_lanes" ADD CONSTRAINT "fk_03367de003b244df4ffc" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."scheduler_lanes" ADD CONSTRAINT "fk_e132a49ffc944332178d" FOREIGN KEY ("workspace_id","principal_id","active_job_id") REFERENCES shiliu."assistant_jobs" ("workspace_id","principal_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."artifact_objects" ADD CONSTRAINT "fk_59fac7164bd6679b9c21" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."artifact_versions" ADD CONSTRAINT "fk_d922ac31f56ee5c6e019" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."artifact_versions" ADD CONSTRAINT "fk_1d787b72b3dc9e6a3ac9" FOREIGN KEY ("workspace_id","video_id") REFERENCES shiliu."videos" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."artifact_versions" ADD CONSTRAINT "fk_f94944ec3dec260724da" FOREIGN KEY ("workspace_id","object_sha256") REFERENCES shiliu."artifact_objects" ("workspace_id","sha256") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."artifact_heads" ADD CONSTRAINT "fk_004eadcf4ad98cc991e0" FOREIGN KEY ("workspace_id","logical_key","artifact_version_id") REFERENCES shiliu."artifact_versions" ("workspace_id","logical_key","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."retrieval_projection_tasks" ADD CONSTRAINT "fk_e17df30794ef91ea3587" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."model_dispatch_receipts" ADD CONSTRAINT "fk_f5f0f27d356cc19a36e1" FOREIGN KEY ("workspace_id","principal_id") REFERENCES shiliu."workspaces" ("id","owner_user_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."model_dispatch_receipts" ADD CONSTRAINT "fk_bb8fa20590d996527c8f" FOREIGN KEY ("workspace_id","run_id") REFERENCES shiliu."assistant_runs" ("workspace_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."model_dispatch_receipts" ADD CONSTRAINT "fk_f609fc1dbadd993f9990" FOREIGN KEY ("workspace_id","principal_id","job_id") REFERENCES shiliu."assistant_jobs" ("workspace_id","principal_id","id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."model_dispatch_receipts" ADD CONSTRAINT "fk_4658c832e9dd11141768" FOREIGN KEY ("workspace_id","principal_id","budget_day","lane") REFERENCES shiliu."assistant_model_budget_days" ("workspace_id","principal_id","budget_date","lane") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."collection_embeddings" ADD CONSTRAINT "fk_fd019a6e5e858a3c4e48" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."collection_embeddings" ADD CONSTRAINT "fk_fa2dfb25d3f795a56fa9" FOREIGN KEY ("profile_id") REFERENCES shiliu."embedding_profiles" ("profile_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."collection_embeddings" ADD CONSTRAINT "fk_f0d33a7b9f4d399497d0" FOREIGN KEY ("workspace_id","unit_id") REFERENCES shiliu."retrieval_units" ("workspace_id","unit_id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."memory_embeddings" ADD CONSTRAINT "fk_1aa029ac51e3a347883e" FOREIGN KEY ("workspace_id") REFERENCES shiliu."workspaces" ("id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."memory_embeddings" ADD CONSTRAINT "fk_2c8b91b22df3568cf8a0" FOREIGN KEY ("profile_id") REFERENCES shiliu."embedding_profiles" ("profile_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."memory_embeddings" ADD CONSTRAINT "fk_e73c7e6d387eed9bbb8b" FOREIGN KEY ("workspace_id","memory_id") REFERENCES shiliu."assistant_memories" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."wiki_windows" ADD CONSTRAINT "fk_24cc6172d8a27f2af605" FOREIGN KEY ("workspace_id","page_id") REFERENCES shiliu."assistant_wiki_pages" ("workspace_id","id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."wiki_embeddings" ADD CONSTRAINT "fk_038c5b14857b15c10ba1" FOREIGN KEY ("window_id") REFERENCES shiliu."wiki_windows" ("window_id") ON DELETE CASCADE DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."wiki_embeddings" ADD CONSTRAINT "fk_046632a8ef4f9e903e18" FOREIGN KEY ("profile_id") REFERENCES shiliu."embedding_profiles" ("profile_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."migration_batches" ADD CONSTRAINT "fk_41b2b501fb0c2fe8ecc9" FOREIGN KEY ("run_id") REFERENCES shiliu."migration_runs" ("run_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE shiliu."migration_exceptions" ADD CONSTRAINT "fk_7ec4654bcb5f2508ead7" FOREIGN KEY ("run_id") REFERENCES shiliu."migration_runs" ("run_id") ON DELETE NO ACTION DEFERRABLE INITIALLY IMMEDIATE;

CREATE TRIGGER "embedding_profiles_no_update" BEFORE UPDATE ON shiliu."embedding_profiles" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE TRIGGER "embedding_profiles_no_delete" BEFORE DELETE ON shiliu."embedding_profiles" FOR EACH ROW EXECUTE FUNCTION shiliu.reject_immutable();

CREATE FUNCTION shiliu."json_scope_45088ea1a2c62dcde7ce"() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN IF jsonb_typeof(NEW."source_ids_json") <> 'array' OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW."source_ids_json") x(id) WHERE NOT EXISTS (SELECT 1 FROM shiliu."favorite_sources" p WHERE p.workspace_id=NEW.workspace_id AND p."id"::text=x.id)) THEN RAISE EXCEPTION 'json_reference_scope' USING ERRCODE='23503'; END IF;IF jsonb_typeof(NEW."video_ids_json") <> 'array' OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW."video_ids_json") x(id) WHERE NOT EXISTS (SELECT 1 FROM shiliu."videos" p WHERE p.workspace_id=NEW.workspace_id AND p."id"::text=x.id)) THEN RAISE EXCEPTION 'json_reference_scope' USING ERRCODE='23503'; END IF; RETURN NEW; END $$;

CREATE TRIGGER "json_scope_45088ea1a2c62dcde7ce" BEFORE INSERT OR UPDATE ON shiliu."assistant_spaces" FOR EACH ROW EXECUTE FUNCTION shiliu."json_scope_45088ea1a2c62dcde7ce"();

CREATE FUNCTION shiliu."json_scope_123fd64207451ba12feb"() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN IF jsonb_typeof(NEW."source_message_ids_json") <> 'array' OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW."source_message_ids_json") x(id) WHERE NOT EXISTS (SELECT 1 FROM shiliu."assistant_messages" p WHERE p.workspace_id=NEW.workspace_id AND p."id"::text=x.id)) THEN RAISE EXCEPTION 'json_reference_scope' USING ERRCODE='23503'; END IF; RETURN NEW; END $$;

CREATE TRIGGER "json_scope_123fd64207451ba12feb" BEFORE INSERT OR UPDATE ON shiliu."assistant_memories" FOR EACH ROW EXECUTE FUNCTION shiliu."json_scope_123fd64207451ba12feb"();

CREATE FUNCTION shiliu."json_scope_6528d20fabf1d0274382"() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN IF jsonb_typeof(NEW."source_message_ids_json") <> 'array' OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW."source_message_ids_json") x(id) WHERE NOT EXISTS (SELECT 1 FROM shiliu."assistant_messages" p WHERE p.workspace_id=NEW.workspace_id AND p."id"::text=x.id)) THEN RAISE EXCEPTION 'json_reference_scope' USING ERRCODE='23503'; END IF; RETURN NEW; END $$;

CREATE TRIGGER "json_scope_6528d20fabf1d0274382" BEFORE INSERT OR UPDATE ON shiliu."assistant_memory_suppressions" FOR EACH ROW EXECUTE FUNCTION shiliu."json_scope_6528d20fabf1d0274382"();

CREATE FUNCTION shiliu."json_scope_a4641ad818e7e72f3f6c"() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN IF jsonb_typeof(NEW."source_run_ids_json") <> 'array' OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(NEW."source_run_ids_json") x(id) WHERE NOT EXISTS (SELECT 1 FROM shiliu."assistant_runs" p WHERE p.workspace_id=NEW.workspace_id AND p."id"::text=x.id AND p.thread_id=NEW.thread_id)) THEN RAISE EXCEPTION 'json_reference_scope' USING ERRCODE='23503'; END IF; RETURN NEW; END $$;

CREATE TRIGGER "json_scope_a4641ad818e7e72f3f6c" BEFORE INSERT OR UPDATE ON shiliu."assistant_task_notes" FOR EACH ROW EXECUTE FUNCTION shiliu."json_scope_a4641ad818e7e72f3f6c"();

CREATE FUNCTION shiliu.check_personal_dependency() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM shiliu.assistant_memories m JOIN shiliu.assistant_wiki_pages p ON p.id=NEW.page_id AND p.workspace_id=m.workspace_id WHERE m.id=NEW.memory_id AND m.workspace_id=NEW.workspace_id AND (m.scope_kind='user' OR m.scope_space_id=p.space_id)) THEN RAISE EXCEPTION 'personal_dependency_scope' USING ERRCODE='23503'; END IF;
 RETURN NEW; END $$;
 CREATE TRIGGER check_personal_dependency BEFORE INSERT OR UPDATE ON shiliu.assistant_wiki_personal_dependencies FOR EACH ROW EXECUTE FUNCTION shiliu.check_personal_dependency();

CREATE INDEX projection_tasks_due ON shiliu.retrieval_projection_tasks(workspace_id,status,not_before);

CREATE SCHEMA shiliu_migration; REVOKE ALL ON SCHEMA shiliu_migration FROM PUBLIC;
